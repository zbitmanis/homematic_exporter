"""Registry behaviour (spec 6, R6-R10, C11) from hand-built snapshots."""

import logging
import math
import threading
from typing import Any

import pytest
from prometheus_client import REGISTRY

from homematic_exporter.config_models import Tuning
from homematic_exporter.contracts import BatteryRecord
from homematic_exporter.metrics import ConfigError, Registry
from tests.metrics.conftest import metric
from tests.metrics.helpers import (
    contact,
    defs,
    device,
    only,
    parse,
    room,
    snapshot,
    valve,
)

TEMP = "homematic_room_temperature_celsius"
LOGGER = "homematic_exporter.metrics.registry"


def reg(*entries: dict[str, Any], tuning: Tuning | None = None, **kw: Any) -> Registry:
    return Registry.build(defs(*entries), tuning or Tuning(), **kw)


def k(**labels: str) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(labels.items()))


def test_gauge_with_room_label() -> None:
    r = reg(metric())
    r.update(snapshot(rooms=(room("kitchen"), room("bath", temperature_celsius=19.0))))
    assert parse(r.exposition())[TEMP] == {k(room="kitchen"): 21.5, k(room="bath"): 19.0}


def test_scale_multiplies_numeric_values() -> None:
    r = reg(metric(name="homematic_room_humidity_ratio", value="humidity", scale=0.01))
    r.update(snapshot(rooms=(room(humidity=55.0),)))
    value = only(parse(r.exposition()), "homematic_room_humidity_ratio")[k(room="kitchen")]
    assert value == pytest.approx(0.55)


@pytest.mark.parametrize(
    ("transform", "raw", "expected"),
    [
        ({"equals": "AUTOMATIC"}, "AUTOMATIC", 1.0),
        ({"equals": "AUTOMATIC"}, "MANUAL", 0.0),
        ({"equals": "AUTOMATIC"}, 1, 0.0),
        ({"in": ["OPEN", "TILTED"]}, "TILTED", 1.0),
        ({"in": ["OPEN", "TILTED"]}, "CLOSED", 0.0),
        ({"equals": 1}, True, 0.0),  # a bool is never equal to a number
        ({"equals": True}, True, 1.0),
        ({"equals": 3}, 3.0, 1.0),
        ("bool", True, 1.0),
        ("bool", False, 0.0),
        ("bool", 0, 0.0),
        ("bool", 2.5, 1.0),
        ("none", 7, 7.0),
        ("none", True, 1.0),
    ],
)
def test_transforms(transform: object, raw: object, expected: float) -> None:
    r = reg(metric(name="homematic_room_probe_state", value="extras.probe", transform=transform))
    r.update(snapshot(rooms=(room(extras={"probe": raw}),)))
    assert only(parse(r.exposition()), "homematic_room_probe_state") == {
        k(room="kitchen"): expected
    }


@pytest.mark.parametrize(
    "raw",
    [None, "text", math.nan, math.inf, -math.inf, 10**400, "bool-ish", [1]],
)
def test_unusable_raw_values_for_none_transform_produce_no_series(raw: object) -> None:
    r = reg(metric(name="homematic_room_probe_state", value="extras.probe"))
    r.update(snapshot(rooms=(room(extras={"probe": raw}),)))
    assert only(parse(r.exposition()), "homematic_room_probe_state") == {}


@pytest.mark.parametrize("raw", ["yes", None, math.nan, math.inf])
def test_bool_transform_rejects_non_boolean_values(raw: object) -> None:
    r = reg(metric(name="homematic_room_probe_state", value="extras.probe", transform="bool"))
    r.update(snapshot(rooms=(room(extras={"probe": raw}),)))
    assert only(parse(r.exposition()), "homematic_room_probe_state") == {}


def test_scale_overflow_produces_no_series() -> None:
    r = reg(metric(value="extras.probe", scale=1e308))
    r.update(snapshot(rooms=(room(extras={"probe": 1e10}),)))
    assert only(parse(r.exposition()), TEMP) == {}


def test_none_value_produces_no_series_and_removes_an_existing_one() -> None:
    r = reg(metric())
    r.update(snapshot(rooms=(room("girts"),)))
    assert k(room="girts") in only(parse(r.exposition()), TEMP)
    r.update(snapshot(rooms=(room("girts", temperature_celsius=None),)))
    assert only(parse(r.exposition()), TEMP) == {}


def test_entities_absent_from_a_new_snapshot_lose_all_their_series() -> None:
    r = reg(
        metric(),
        metric(
            name="homematic_device_rssi_dbm",
            scope="devices",
            value="rssi_dbm",
            labels=["room", "device_type", "device"],
        ),
    )
    r.update(snapshot(rooms=(room("a"), room("b")), devices=(device(), device("x y", "b"))))
    r.update(snapshot(rooms=(room("b"),), devices=(device("x y", "b"),)))
    series = parse(r.exposition())
    assert set(series[TEMP]) == {k(room="b")}
    assert len(series["homematic_device_rssi_dbm"]) == 1


def test_extras_only_metric_appears_when_added_by_config() -> None:
    snap = snapshot(rooms=(room(extras={"boost_duration": 30.0}),))
    without = reg(metric())
    without.update(snap)
    assert "homematic_room_boost_duration_seconds" not in parse(without.exposition())
    added = reg(
        metric(),
        metric(name="homematic_room_boost_duration_seconds", value="extras.boost_duration"),
    )
    added.update(snap)
    series = parse(added.exposition())
    assert series["homematic_room_boost_duration_seconds"] == {k(room="kitchen"): 30.0}


def test_extras_missing_on_an_entity_means_no_series_for_it() -> None:
    r = reg(metric(name="homematic_room_boost_duration_seconds", value="extras.boost_duration"))
    r.update(snapshot(rooms=(room("a", extras={"boost_duration": 5}), room("b"))))
    series = parse(r.exposition())
    assert series["homematic_room_boost_duration_seconds"] == {k(room="a"): 5.0}


def test_device_valve_and_contact_scopes_carry_all_three_labels() -> None:
    labels = ["room", "device_type", "device"]
    r = reg(
        metric(
            name="homematic_device_low_battery",
            scope="devices",
            value="low_battery",
            transform="bool",
            labels=labels,
        ),
        metric(
            name="homematic_valve_position_ratio",
            scope="valves",
            value="position_ratio",
            labels=labels,
        ),
        metric(
            name="homematic_contact_open",
            scope="contacts",
            value="window_state",
            transform={"in": ["OPEN", "TILTED"]},
            labels=labels,
        ),
    )
    r.update(
        snapshot(
            devices=(device(low_battery=True),),
            valves=(valve(),),
            contacts=(contact(window_state="TILTED"),),
        )
    )
    s = parse(r.exposition())
    assert s["homematic_device_low_battery"] == {
        k(room="kitchen", device_type="wall-thermostat", device="kitchen wall-thermostat"): 1.0
    }
    assert s["homematic_valve_position_ratio"] == {
        k(room="kitchen", device_type="floor-valve", device="kitchen floor-valve"): 0.4
    }
    assert list(s["homematic_contact_open"].values()) == [1.0]


def test_battery_metrics_read_battery_records() -> None:
    labels = ["room", "device_type", "device"]
    r = reg(
        metric(
            name="homematic_device_battery_low_since_timestamp_seconds",
            scope="batteries",
            value="low_since",
            labels=labels,
        ),
        metric(
            name="homematic_device_battery_last_replaced_timestamp_seconds",
            scope="batteries",
            value="last_replaced",
            labels=labels,
        ),
    )
    records = (
        BatteryRecord("a b", "a", "wall-thermostat", 1000.0, None),
        BatteryRecord("c d", "c", "wall-thermostat", None, 2000.0),
    )
    r.update(snapshot(), records)
    s = parse(r.exposition())
    assert list(s["homematic_device_battery_low_since_timestamp_seconds"].values()) == [1000.0]
    assert list(s["homematic_device_battery_last_replaced_timestamp_seconds"].values()) == [2000.0]
    r.update(snapshot())  # no records: series removed
    assert "homematic_device_battery_low_since_timestamp_seconds" not in parse(r.exposition())


def test_only_whitelisted_label_names_are_ever_exported() -> None:
    labels = ["room", "device_type", "device"]
    r = reg(
        metric(name="homematic_device_rssi_dbm", scope="devices", value="rssi_dbm", labels=labels),
        metric(),
    )
    r.update(snapshot(rooms=(room(),), devices=(device(),)))
    r.record_success(1_700_000_000.0, 0.5)
    names = {key for series in parse(r.exposition()).values() for s in series for key, _ in s}
    assert names <= {"room", "device_type", "device", "version"}


def test_duplicate_label_sets_keep_the_first_series_and_warn_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    r = reg(
        metric(name="homematic_device_rssi_dbm", scope="devices", value="rssi_dbm", labels=["room"])
    )
    snap = snapshot(devices=(device("a", rssi_dbm=-50), device("b", rssi_dbm=-70)))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        r.update(snap)
        r.update(snap)
    assert parse(r.exposition())["homematic_device_rssi_dbm"] == {k(room="kitchen"): -50.0}
    assert caplog.text.count("same label values") == 1


def test_hostile_label_and_help_text_stays_valid_exposition() -> None:
    nasty = 'a"b\\c\nd'
    r = reg(metric(help='line1\nline2 \\ "q"'))
    r.update(snapshot(rooms=(room(nasty),)))
    assert parse(r.exposition())[TEMP] == {k(room=nasty): 21.5}


def test_series_are_sorted_for_stable_output() -> None:
    r = reg(metric())
    r.update(snapshot(rooms=(room("b"), room("a"), room("c"))))
    lines = [x for x in r.exposition().decode().splitlines() if x.startswith(TEMP)]
    assert lines == sorted(lines)


def test_build_rejects_invalid_definitions() -> None:
    with pytest.raises(ConfigError, match=r"metrics\[0\]\.labels\[0\]: unknown label 'sgtin'"):
        reg(metric(labels=["sgtin"]))
    with pytest.raises(ConfigError, match="duplicate metric name"):
        reg(metric(), metric())


# --- derived metrics (6.5) ---------------------------------------------------------------


def test_valves_open_counts_positions_above_the_threshold() -> None:
    r = reg(tuning=Tuning(heat_demand_min_position=0.1))
    valves = (valve("a", 0.5), valve("b", 0.1), valve("c", 0.0), valve("d", None))
    r.update(snapshot(valves=valves))
    s = parse(r.exposition())
    assert s["homematic_valves_open"] == {(): 1.0}
    assert s["homematic_heat_demand"] == {(): 1.0}


def test_no_open_valve_means_no_heat_demand() -> None:
    r = reg()
    r.update(snapshot(valves=(valve("a", 0.0),)))
    s = parse(r.exposition())
    assert s["homematic_valves_open"] == {(): 0.0}
    assert s["homematic_heat_demand"] == {(): 0.0}


def test_non_finite_positions_are_not_counted_as_open() -> None:
    r = reg()
    r.update(snapshot(valves=(valve("a", math.nan), valve("b", math.inf))))
    assert parse(r.exposition())["homematic_valves_open"] == {(): 0.0}


def test_derived_metrics_are_absent_before_the_first_update() -> None:
    s = parse(reg().exposition())
    assert "homematic_valves_open" not in s
    assert "homematic_heat_demand" not in s


# --- meta metrics (6.6) ------------------------------------------------------------------


def test_fresh_registry_exports_only_errors_and_build_info() -> None:
    s = parse(reg(version="1.2.3").exposition())
    assert set(s) == {"homematic_poll_errors_total", "homematic_exporter_build_info"}
    assert s["homematic_poll_errors_total"] == {(): 0.0}
    assert s["homematic_exporter_build_info"] == {k(version="1.2.3"): 1.0}


def test_default_version_is_dev_and_long_versions_are_cut() -> None:
    assert k(version="dev") in parse(reg().exposition())["homematic_exporter_build_info"]
    s = parse(reg(version="v" * 1000).exposition())["homematic_exporter_build_info"]
    assert len(next(iter(s))[0][1]) == 100


def test_data_age_has_no_series_before_the_first_success() -> None:
    now = [5_000.0]
    r = reg(clock=lambda: now[0])
    s = parse(r.exposition())
    assert "homematic_data_age_seconds" not in s
    assert "homematic_last_successful_poll_timestamp_seconds" not in s
    assert "homematic_poll_duration_seconds" not in s
    r.record_success(4_990.0, 1.25)
    now[0] = 5_030.0
    s = parse(r.exposition())
    assert s["homematic_data_age_seconds"] == {(): 40.0}
    assert s["homematic_last_successful_poll_timestamp_seconds"] == {(): 4_990.0}
    assert s["homematic_poll_duration_seconds"] == {(): 1.25}


def test_data_age_is_computed_at_scrape_time_and_never_negative() -> None:
    now = [100.0]
    r = reg(clock=lambda: now[0])
    r.record_success(100.0, 0.1)
    now[0] = 160.0
    assert parse(r.exposition())["homematic_data_age_seconds"] == {(): 60.0}
    now[0] = 50.0  # clock stepped back
    assert parse(r.exposition())["homematic_data_age_seconds"] == {(): 0.0}


def test_errors_are_counted_and_do_not_touch_the_success_timestamp() -> None:
    r = reg()
    r.record_success(1000.0, 0.2)
    r.record_error()
    r.record_error()
    s = parse(r.exposition())
    assert s["homematic_poll_errors_total"] == {(): 2.0}
    assert s["homematic_last_successful_poll_timestamp_seconds"] == {(): 1000.0}


@pytest.mark.parametrize(
    ("timestamp", "duration"),
    [
        (math.nan, 1.0),
        (math.inf, 1.0),
        (-1.0, 1.0),
        (5e9, 1.0),
        (1000.0, math.nan),
        (1000.0, -0.1),
        (1000.0, math.inf),
    ],
)
def test_record_success_rejects_invalid_numbers_without_changing_state(
    timestamp: float, duration: float
) -> None:
    r = reg()
    r.record_success(1000.0, 0.5)
    with pytest.raises(ValueError, match="invalid"):
        r.record_success(timestamp, duration)
    assert parse(r.exposition())["homematic_last_successful_poll_timestamp_seconds"] == {(): 1000.0}


def test_registry_is_private_and_instances_are_independent() -> None:
    a, b = reg(metric()), reg(metric())
    a.update(snapshot(rooms=(room(),)))
    assert TEMP in parse(a.exposition())
    assert TEMP not in parse(b.exposition())
    assert not any(m.name.startswith("homematic") for m in REGISTRY.collect())


# --- C11 and logging ------------------------------------------------------------------------


def test_zero_series_on_two_consecutive_updates_warns_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    r = reg(metric(value="extras.typo"))
    snap = snapshot(rooms=(room(),))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        r.update(snap)
        assert caplog.text == ""
        r.update(snap)
        r.update(snap)
    assert caplog.text.count(TEMP) == 1
    assert "no series" in caplog.text


def test_warning_streak_resets_when_series_return(caplog: pytest.LogCaptureFixture) -> None:
    r = reg(metric(value="extras.maybe"))
    empty, full = snapshot(rooms=(room(),)), snapshot(rooms=(room(extras={"maybe": 1.0}),))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        r.update(empty)
        r.update(full)
        r.update(empty)
    assert caplog.text == ""


def test_no_warning_when_the_scope_has_no_entities(caplog: pytest.LogCaptureFixture) -> None:
    r = reg(
        metric(
            name="homematic_contact_open", scope="contacts", value="window_state", labels=["room"]
        )
    )
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        for _ in range(3):
            r.update(snapshot())
    assert caplog.text == ""


def test_first_update_logs_the_series_count(caplog: pytest.LogCaptureFixture) -> None:
    r = reg(metric())
    with caplog.at_level(logging.INFO, logger=LOGGER):
        r.update(snapshot(rooms=(room("a"), room("b"))))
        r.update(snapshot(rooms=(room("a"), room("b"))))
    assert caplog.text.count("series") == 1
    assert "4 series" in caplog.text  # 2 entity series + valves_open + heat_demand


def test_logs_do_not_contain_label_values(caplog: pytest.LogCaptureFixture) -> None:
    r = reg(metric(value="extras.typo"))
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        for _ in range(3):
            r.update(snapshot(rooms=(room("secret-room-name"),)))
    assert "secret-room-name" not in caplog.text


# --- concurrency ----------------------------------------------------------------------------


def test_scrapes_during_updates_always_see_one_consistent_snapshot() -> None:
    r = reg(metric(), metric(name="homematic_room_setpoint_celsius", value="setpoint_celsius"))
    a = snapshot(
        rooms=tuple(room(f"a{i}", temperature_celsius=1.0, setpoint_celsius=1.0) for i in range(30))
    )
    b = snapshot(
        rooms=tuple(room(f"b{i}", temperature_celsius=2.0, setpoint_celsius=2.0) for i in range(30))
    )
    r.update(a)
    stop = threading.Event()
    failures: list[str] = []

    def writer() -> None:
        while not stop.is_set():
            r.update(b)
            r.update(a)
            r.record_error()

    def reader() -> None:
        for _ in range(300):
            s = parse(r.exposition())
            temps, setpoints = s[TEMP], s["homematic_room_setpoint_celsius"]
            prefixes = {dict(key)["room"][0] for key in temps}
            if len(prefixes) != 1 or set(temps) != set(setpoints):
                failures.append(f"mixed snapshot: {prefixes}")

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        reader()
    finally:
        stop.set()
        thread.join()
    assert failures == []
