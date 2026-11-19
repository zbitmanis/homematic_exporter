import copy
import logging
import math
import time
from typing import Any

import pytest

from homematic_exporter.config_models import ExtractConfig
from homematic_exporter.contracts import (
    Contact,
    Device,
    NameCollisionError,
    Room,
    Snapshot,
    UpstreamError,
    Valve,
)
from homematic_exporter.source.parser import (
    MAX_NAME_CHARS,
    parse_snapshot,
    parse_with_report,
)

from .conftest import device, make_state

NOW = 1_795_000_000.0
OK = (False, False, False)  # low battery, unreachable, undervoltage
LOW = (True, False, False)
GONE = (False, True, False)
NOBAT = (None, False, False)
FLOOR = "FLOOR_TERMINAL_BLOCK_MECHANIC_CHANNEL"


def dev(
    name: str, room: str, dtype: str, flags: tuple[bool | None, ...], rssi: int | None
) -> Device:
    low, unreach, under = flags
    return Device(name, room, dtype, low, unreach, under, rssi, {})


def test_golden_snapshot_for_mini_state(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    snap = parse_snapshot(mini_state, NOW, default_extract)

    assert snap == Snapshot(
        taken_at=NOW,
        rooms=(
            Room("kitchen", 21.3, 20.0, 50.0, "AUTOMATIC", None, {}),
            Room("bedroom", 19.8, 19.0, 45.0, "MANUAL", None, {}),
            Room("hall", None, None, None, "AUTOMATIC", "CLOSED", {}),
        ),
        devices=(
            dev("kitchen wall-thermostat", "kitchen", "wall-thermostat", OK, -60),
            dev("bedroom temp-humidity-display", "bedroom", "temp-humidity-display", LOW, -70),
            dev("bedroom radiator-thermostat", "bedroom", "radiator-thermostat", OK, -55),
            dev("hall temp-humidity-sensor", "hall", "temp-humidity-sensor", GONE, None),
            dev("hall door-window-contact", "hall", "door-window-contact", OK, -62),
            dev("system floor-controller", "system", "floor-controller", OK, -70),
            dev("system circulation-pump-switch", "system", "circulation-pump-switch", NOBAT, -48),
            dev("hall hmip-new-1", "hall", "hmip-new-1", OK, -66),
            dev("system access-point", "system", "access-point", NOBAT, None),
            dev("bedroom door-window-contact", "bedroom", "door-window-contact", OK, -58),
        ),
        valves=(  # device order, then channel order
            Valve("bedroom", "radiator-thermostat", "bedroom radiator-thermostat", 0.3, 20.1, {}),
            Valve("kitchen", "floor-valve", "kitchen floor-valve", 0.1, None, {}),
            Valve("hall", "floor-valve", "hall floor-valve", 0.0, None, {}),
        ),
        contacts=(
            Contact("hall", "door-window-contact", "hall door-window-contact", "CLOSED", {}),
            Contact("bedroom", "door-window-contact", "bedroom door-window-contact", "OPEN", {}),
        ),
    )


def test_device_names_are_unique_and_valves_skip_unused_channel(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    snap = parse_snapshot(mini_state, NOW, default_extract)
    names = [d.name for d in snap.devices]
    assert len(names) == len(set(names)) == 10
    assert [v.device for v in snap.valves].count("kitchen floor-valve") == 1
    assert len(snap.valves) == 3  # channel 3 has no group: skipped


def test_device_in_several_rooms_or_none_gets_system_room(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    snap = parse_snapshot(mini_state, NOW, default_extract)
    by_name = {d.name: d for d in snap.devices}
    assert by_name["system floor-controller"].room == "system"  # kitchen and hall
    assert by_name["system access-point"].room == "system"  # no room


def test_custom_system_room_name(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    cfg = ExtractConfig.model_validate({**default_extract.model_dump(), "system_room": "house"})
    snap = parse_snapshot(mini_state, NOW, cfg)
    assert "house access-point" in {d.name for d in snap.devices}


def test_unmapped_model_is_lowercased_and_reported_once_per_parse(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    snap, report = parse_with_report(mini_state, NOW, default_extract)
    assert any(d.device_type == "hmip-new-1" for d in snap.devices)
    assert report.unmapped_models == ("HmIP-NEW-1",)
    assert report.collisions == ()


def test_extras_are_read_per_scope(
    mini_state: dict[str, Any], extract_with_extras: ExtractConfig
) -> None:
    state = copy.deepcopy(mini_state)
    state["devices"]["ID-0001"]["functionalChannels"]["0"]["rssiPeerValue"] = -61
    state["devices"]["ID-0010"]["functionalChannels"]["1"]["sabotage"] = True
    snap = parse_snapshot(state, NOW, extract_with_extras)

    assert snap.rooms[0].extras == {"boost_duration": 15.0}
    assert snap.rooms[1].extras == {"boost_duration": None}  # missing -> None, never raises
    assert snap.devices[0].extras == {"rssi_peer": -61.0}
    assert snap.valves[0].extras == {"valve_state": "ADAPTION_DONE"}
    assert snap.contacts[1].extras == {"sabotage": True}
    assert snap.contacts[0].extras == {"sabotage": None}


def test_extras_are_read_only(
    mini_state: dict[str, Any], extract_with_extras: ExtractConfig
) -> None:
    snap = parse_snapshot(mini_state, NOW, extract_with_extras)
    with pytest.raises(TypeError):
        snap.rooms[0].extras["x"] = 1  # type: ignore[index]


def test_parse_does_not_mutate_input(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    before = copy.deepcopy(mini_state)
    parse_snapshot(mini_state, NOW, default_extract)
    assert mini_state == before


def test_unconfigured_attribute_maps_to_none(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    data = default_extract.model_dump()
    data["rooms"] = {"temperature_celsius": "actualTemperature"}
    data["device_flags"] = {}
    snap = parse_snapshot(mini_state, NOW, ExtractConfig.model_validate(data))
    assert snap.rooms[0] == Room("kitchen", 21.3, None, None, None, None, {})
    assert snap.devices[0].low_battery is None
    assert snap.devices[0].rssi_dbm is None


# --- collisions -------------------------------------------------------------------------------


def test_collision_error_policy_raises_with_names(
    collision_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    with pytest.raises(NameCollisionError) as err:
        parse_snapshot(collision_state, NOW, default_extract, "error")
    assert err.value.names == ("kitchen wall-thermostat",)


def test_collision_is_the_default_policy(
    collision_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    with pytest.raises(NameCollisionError):
        parse_snapshot(collision_state, NOW, default_extract)


def test_collision_suffix_orders_by_sgtin(
    collision_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    snap, report = parse_with_report(collision_state, NOW, default_extract, "suffix")
    kitchen = [d.name for d in snap.devices if d.room == "kitchen"]
    assert kitchen == ["kitchen wall-thermostat", "kitchen wall-thermostat-2"]
    assert report.collisions == ("kitchen wall-thermostat",)


def test_collision_suffix_is_stable_when_input_order_changes(
    collision_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    # SGTIN-0001 is the base name, SGTIN-0011 the suffixed one, whatever the dict order.
    reversed_state = copy.deepcopy(collision_state)
    reversed_state["devices"] = dict(reversed(list(reversed_state["devices"].items())))
    snap = parse_snapshot(reversed_state, NOW, default_extract, "suffix")
    by_label = {d.name: d for d in snap.devices}
    assert by_label["kitchen wall-thermostat"].rssi_dbm == -60
    assert "kitchen wall-thermostat-2" in by_label


def test_suffix_skips_names_already_taken(default_extract: ExtractConfig) -> None:
    state = make_state(A=device("HmIP-STH"), B=device("HmIP-STH"), C=device("HmIP-STH-2"))
    cfg = ExtractConfig.model_validate(
        {
            **default_extract.model_dump(),
            "device_models": {
                "HmIP-STH": "sensor",
                "HmIP-STH-2": "sensor-2",
            },
        }
    )
    snap = parse_snapshot(state, NOW, cfg, "suffix")
    # "lab sensor-2" belongs to C, so the second sensor must become "-3", not steal it.
    assert [d.name for d in snap.devices] == ["lab sensor", "lab sensor-3", "lab sensor-2"]


def test_collision_renames_dependent_valves_and_contacts(
    collision_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    state = copy.deepcopy(collision_state)
    twin = state["devices"]["ID-0011"]
    twin["modelType"] = "HmIP-SWDM-2"
    twin["functionalChannels"]["1"] = {
        "functionalChannelType": "SHUTTER_CONTACT_CHANNEL",
        "groups": ["ID-0201"],
        "windowState": "TILTED",
    }
    original = state["devices"]["ID-0001"]
    original["modelType"] = "HmIP-SWDM-2"
    original["functionalChannels"]["1"] = {
        "functionalChannelType": "SHUTTER_CONTACT_CHANNEL",
        "groups": ["ID-0201"],
        "windowState": "CLOSED",
    }
    snap = parse_snapshot(state, NOW, default_extract, "suffix")
    kitchen = {c.device: c.window_state for c in snap.contacts if c.room == "kitchen"}
    assert kitchen == {
        "kitchen door-window-contact": "CLOSED",
        "kitchen door-window-contact-2": "TILTED",
    }


def test_two_floor_channels_in_one_room_collide(default_extract: ExtractConfig) -> None:
    state = make_state(F=device("HmIP-FALMOT-C12", lowBat=False))
    state["devices"]["F"]["functionalChannels"].update(
        {
            "1": {"functionalChannelType": FLOOR, "groups": ["G1"], "valvePosition": 0.2},
            "2": {"functionalChannelType": FLOOR, "groups": ["G1"], "valvePosition": 0.4},
        }
    )
    cfg = default_extract
    with pytest.raises(NameCollisionError) as err:
        parse_snapshot(state, NOW, cfg, "error")
    assert err.value.names == ("lab floor-valve",)
    snap = parse_snapshot(state, NOW, cfg, "suffix")
    assert [(v.device, v.position_ratio) for v in snap.valves] == [
        ("lab floor-valve", 0.2),
        ("lab floor-valve-2", 0.4),
    ]


def test_duplicate_room_labels_collide(default_extract: ExtractConfig) -> None:
    state = make_state()
    state["groups"]["G2"] = {"id": "G2", "type": "HEATING", "label": "lab", "channels": []}
    with pytest.raises(NameCollisionError) as err:
        parse_snapshot(state, NOW, default_extract, "error")
    assert err.value.names == ("lab",)
    snap = parse_snapshot(state, NOW, default_extract, "suffix")
    assert [r.name for r in snap.rooms] == ["lab", "lab-2"]


# --- None handling and hostile input ------------------------------------------------------------


@pytest.mark.parametrize("raw", [None, [], "x", 5, {}, {"devices": {}}, {"groups": {}}])
def test_structurally_wrong_payload_raises_upstream_error(
    raw: Any, default_extract: ExtractConfig
) -> None:
    with pytest.raises(UpstreamError):
        parse_snapshot(raw, NOW, default_extract)


@pytest.mark.parametrize("bad", [{"devices": [], "groups": {}}, {"devices": {}, "groups": "x"}])
def test_wrong_section_types_raise_upstream_error(
    bad: dict[str, Any], default_extract: ExtractConfig
) -> None:
    with pytest.raises(UpstreamError):
        parse_snapshot(bad, NOW, default_extract)


def test_empty_home_is_an_empty_snapshot(default_extract: ExtractConfig) -> None:
    snap = parse_snapshot({"devices": {}, "groups": {}}, NOW, default_extract)
    assert snap == Snapshot(NOW, (), (), (), ())


@pytest.mark.parametrize(
    "value", ["21", True, False, [1], {"a": 1}, math.nan, math.inf, -math.inf, 10**400]
)
def test_non_numeric_or_non_finite_numbers_become_none(
    value: Any, mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    state = copy.deepcopy(mini_state)
    state["groups"]["ID-0201"]["actualTemperature"] = value
    state["devices"]["ID-0003"]["functionalChannels"]["1"]["valvePosition"] = value
    snap = parse_snapshot(state, NOW, default_extract)
    assert snap.rooms[0].temperature_celsius is None
    assert (
        next(v for v in snap.valves if v.device_type == "radiator-thermostat").position_ratio
        is None
    )


def test_wrong_typed_strings_flags_and_rssi_become_none(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    state = copy.deepcopy(mini_state)
    state["groups"]["ID-0201"]["controlMode"] = 5
    state["groups"]["ID-0201"]["windowState"] = ["OPEN"]
    base = state["devices"]["ID-0001"]["functionalChannels"]["0"]
    base.update(lowBat="yes", unreach=1, deviceUndervoltage=None, rssiDeviceValue="-60")
    snap = parse_snapshot(state, NOW, default_extract)
    assert snap.rooms[0].control_mode is None
    assert snap.rooms[0].window_state is None
    dev = snap.devices[0]
    assert (dev.low_battery, dev.unreachable, dev.undervoltage, dev.rssi_dbm) == (None,) * 4


def test_rssi_float_with_integer_value_is_accepted_other_floats_not(
    default_extract: ExtractConfig,
) -> None:
    state = make_state(
        A=device(rssiDeviceValue=-60.0), B=device("HmIP-STHD", rssiDeviceValue=-60.5)
    )
    snap = parse_snapshot(state, NOW, default_extract)
    assert [d.rssi_dbm for d in snap.devices] == [-60, None]


def test_extras_reject_non_scalar_and_non_finite(
    mini_state: dict[str, Any], extract_with_extras: ExtractConfig
) -> None:
    state = copy.deepcopy(mini_state)
    state["groups"]["ID-0201"]["boostDuration"] = {"nested": [1]}
    state["groups"]["ID-0202"]["boostDuration"] = math.nan
    state["groups"]["ID-0203"]["boostDuration"] = "text"
    snap = parse_snapshot(state, NOW, extract_with_extras)
    assert [r.extras["boost_duration"] for r in snap.rooms] == [None, None, "text"]


def test_missing_or_hostile_device_structure_never_raises(default_extract: ExtractConfig) -> None:
    state = make_state(
        A={"modelType": "HmIP-STH"},  # no channels
        B={"modelType": "HmIP-STH", "functionalChannels": []},
        C={"modelType": "HmIP-STH", "functionalChannels": {"0": "x", "1": None, "2": {}}},
        D={"modelType": None, "functionalChannels": {"0": {"functionalChannelType": 7}}},
        E={"modelType": "", "functionalChannels": {"x": {"functionalChannelType": "DEVICE_BASE"}}},
    )
    state["devices"]["F"] = "not a dict"
    state["devices"]["G"] = None
    snap = parse_snapshot(state, NOW, default_extract, "suffix")
    assert len(snap.devices) == 5
    assert all(d.low_battery is None for d in snap.devices[:4])
    assert {d.device_type for d in snap.devices[3:]} == {"unknown"}


def test_hostile_groups_are_ignored(default_extract: ExtractConfig) -> None:
    state = make_state(A=device())
    junk_channels = [None, "x", {"deviceId": 3}, {}, {"deviceId": "A"}]
    state["groups"].update(
        {
            "X1": "str",
            "X2": None,
            "X3": {"type": "HEATING"},  # no label
            "X4": {"type": "HEATING", "label": ""},  # empty label
            "X5": {"type": "HEATING", "label": 7},
            "X6": {"type": "HEATING", "label": "ok", "channels": "nope"},
            "X7": {"type": "HEATING", "label": "ok2", "channels": junk_channels},
            "X8": {"type": ["HEATING"], "label": "bad-type"},
        }
    )
    snap = parse_snapshot(state, NOW, default_extract)
    assert [r.name for r in snap.rooms] == ["lab", "ok", "ok2"]
    assert snap.devices[0].room == "system"  # in lab and ok2


def test_channel_groups_with_unknown_or_non_heating_groups_skip_the_valve(
    default_extract: ExtractConfig,
) -> None:
    state = make_state(F=device("HmIP-FALMOT-C12"))
    state["groups"]["B"] = {"id": "B", "type": "BOILER", "label": "boiler", "channels": []}
    chans = state["devices"]["F"]["functionalChannels"]
    ctype = FLOOR
    chans["1"] = {
        "functionalChannelType": ctype,
        "groups": ["B", "missing", 3, None],
        "valvePosition": 1,
    }
    chans["2"] = {"functionalChannelType": ctype, "groups": "G1", "valvePosition": 1}
    chans["3"] = {"functionalChannelType": ctype, "groups": ["B", "G1"], "valvePosition": 0.5}
    snap = parse_snapshot(state, NOW, default_extract)
    assert [(v.room, v.position_ratio) for v in snap.valves] == [("lab", 0.5)]


def test_floor_valve_in_two_rooms_is_skipped(default_extract: ExtractConfig) -> None:
    state = make_state(F=device("HmIP-FALMOT-C12"))
    state["groups"]["G2"] = {"id": "G2", "type": "HEATING", "label": "den", "channels": []}
    chans = state["devices"]["F"]["functionalChannels"]
    chans["1"] = {
        "functionalChannelType": "FLOOR_TERMINAL_BLOCK_MECHANIC_CHANNEL",
        "groups": ["G1", "G2"],
        "valvePosition": 1,
    }
    assert parse_snapshot(state, NOW, default_extract).valves == ()


def test_huge_input_stays_fast(default_extract: ExtractConfig) -> None:
    devices = {f"D{i}": device("HmIP-STH", lowBat=False) for i in range(2000)}
    state = make_state(**devices)
    start = time.perf_counter()
    snap = parse_snapshot(state, NOW, default_extract, "suffix")
    assert time.perf_counter() - start < 2.0
    assert len(snap.devices) == 2000
    assert len({d.name for d in snap.devices}) == 2000


def test_deeply_nested_values_are_harmless(default_extract: ExtractConfig) -> None:
    nested: Any = []
    for _ in range(100_000):
        nested = [nested]
    state = make_state(A=device())
    state["devices"]["A"]["junk"] = nested
    state["groups"]["G1"]["actualTemperature"] = nested
    snap = parse_snapshot(state, NOW, default_extract)
    assert snap.rooms[0].temperature_celsius is None


def test_result_contains_no_identifiers(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    text = repr(parse_snapshot(mini_state, NOW, default_extract))
    for dev_id, dev in mini_state["devices"].items():
        assert dev_id not in text
        assert dev["serializedGlobalTradeItemNumber"] not in text


def test_parser_logs_nothing_itself(
    collision_state: dict[str, Any],
    default_extract: ExtractConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        parse_snapshot(collision_state, NOW, default_extract, "suffix")
    assert caplog.records == []  # logging once per collision is the sources' job


# --- fix round 1 -------------------------------------------------------------------------------


def _printable(text: str) -> bool:
    return text.isprintable()


def test_long_and_control_character_labels_are_bounded_and_printable(
    default_extract: ExtractConfig,
) -> None:
    state = make_state(A=device())
    state["groups"]["G1"]["label"] = "x" * 5000
    state["groups"]["G2"] = {
        "id": "G2",
        "type": "HEATING",
        "label": "a\nb\x1b[31mc",
        "channels": [],
    }
    snap = parse_snapshot(state, NOW, default_extract)
    for room in snap.rooms:
        assert len(room.name) <= MAX_NAME_CHARS
        assert room.name.isprintable()
    for dev in snap.devices:
        assert dev.name.isprintable()
        assert len(dev.name) <= 2 * MAX_NAME_CHARS + 1
    assert "\x1b" not in "".join(r.name for r in snap.rooms)


def test_hostile_unmapped_model_is_bounded_and_printable(default_extract: ExtractConfig) -> None:
    state = make_state(A={"modelType": "M" * 5000 + "\n\x1b[0m"})
    snap, report = parse_with_report(state, NOW, default_extract)
    assert len(snap.devices[0].device_type) <= MAX_NAME_CHARS
    assert snap.devices[0].device_type.isprintable()
    assert all(len(m) <= MAX_NAME_CHARS and m.isprintable() for m in report.unmapped_models)


def test_collision_error_message_is_bounded_for_1000_collisions(
    default_extract: ExtractConfig,
) -> None:
    state = make_state()
    for i in range(1000):
        for suffix in ("a", "b"):
            gid = f"H{i}{suffix}"
            state["groups"][gid] = {
                "id": gid,
                "type": "HEATING",
                "label": f"{i}" + "L" * 5000,
                "channels": [],
            }
    with pytest.raises(NameCollisionError) as err:
        parse_snapshot(state, NOW, default_extract, "error")
    assert len(str(err.value)) < 10_000
    assert str(err.value).isprintable()


def test_hostile_channel_key_does_not_raise(default_extract: ExtractConfig) -> None:
    state = make_state(A=device(lowBat=True))
    state["devices"]["A"]["functionalChannels"]["9" * 5000] = {"functionalChannelType": "X"}
    state["devices"]["A"]["functionalChannels"]["\u0661"] = {"functionalChannelType": "X"}
    snap = parse_snapshot(state, NOW, default_extract)
    assert snap.devices[0].low_battery is True


def test_not_a_configuration_error_bodies_name_type_and_keys(
    default_extract: ExtractConfig,
) -> None:
    with pytest.raises(UpstreamError) as err:
        parse_snapshot([1, 2], NOW, default_extract)
    assert "list" in err.value.body
    with pytest.raises(UpstreamError) as err:
        parse_snapshot({"errorCode": "SECRETVALUE", "devices": {}}, NOW, default_extract)
    assert "errorCode" in err.value.body
    assert "SECRETVALUE" not in err.value.body
    assert len(err.value.body) < 1000


def test_error_body_with_many_hostile_keys_is_bounded(default_extract: ExtractConfig) -> None:
    raw = {f"k{i}" + "x" * 500 + "\n": 1 for i in range(10_000)}
    with pytest.raises(UpstreamError) as err:
        parse_snapshot(raw, NOW, default_extract)
    assert len(err.value.body) < 2000
    assert err.value.body.isprintable()


def test_suffix_never_steals_a_name_that_really_exists(default_extract: ExtractConfig) -> None:
    state = make_state()
    for gid, label in (("G1", "a"), ("G2", "a"), ("G3", "a-2"), ("G4", "a-2")):
        state["groups"][gid] = {"id": gid, "type": "HEATING", "label": label, "channels": []}
    del state["groups"]["G1"]["channels"][:]
    state["groups"]["G1"]["label"] = "a"
    snap = parse_snapshot(state, NOW, default_extract, "suffix")
    assert [r.name for r in snap.rooms] == ["a", "a-3", "a-2", "a-2-2"]


def test_many_distinct_unmapped_models_are_fast(default_extract: ExtractConfig) -> None:
    devices = {f"D{i}": {"modelType": f"M{i}"} for i in range(30_000)}
    state = make_state(**devices)
    start = time.perf_counter()
    parse_snapshot(state, NOW, default_extract, "suffix")
    assert time.perf_counter() - start < 3.0


def test_unlabelled_heating_group_is_not_a_room_so_the_device_gets_the_labelled_one(
    default_extract: ExtractConfig,
) -> None:
    state = make_state(A=device())
    state["groups"]["U"] = {"id": "U", "type": "HEATING", "channels": [{"deviceId": "A"}]}
    snap = parse_snapshot(state, NOW, default_extract)
    assert snap.devices[0].room == "lab"


def test_model_with_surrounding_whitespace_is_unmapped(default_extract: ExtractConfig) -> None:
    state = make_state(A={"modelType": " HmIP-STH "})
    snap, report = parse_with_report(state, NOW, default_extract)
    assert snap.devices[0].device_type == "hmip-sth"
    assert len(report.unmapped_models) == 1


def test_system_room_device_collides_with_a_real_room_named_system(
    default_extract: ExtractConfig,
) -> None:
    state = make_state(A=device("HmIP-WTH-1"), B=device("HmIP-WTH-1"))
    state["groups"]["G1"]["label"] = "system"
    state["groups"]["G1"]["channels"].pop()  # B is in no room: falls back to the system room
    with pytest.raises(NameCollisionError) as err:
        parse_snapshot(state, NOW, default_extract, "error")
    assert err.value.names == ("system wall-thermostat",)
    snap = parse_snapshot(state, NOW, default_extract, "suffix")
    assert {d.name for d in snap.devices} == {"system wall-thermostat", "system wall-thermostat-2"}


def test_package_exports_parse_with_report() -> None:
    import homematic_exporter.source as pkg

    assert "parse_with_report" in pkg.__all__


def test_joiner_characters_and_legitimate_names_survive(default_extract: ExtractConfig) -> None:
    family = "Familie \U0001f468\u200d\U0001f469\u200d\U0001f467"
    persian = "\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645"
    state = make_state()
    for gid, label in (("G1", family), ("G2", persian), ("G3", "soft\u00adhyphen")):
        state["groups"][gid] = {"id": gid, "type": "HEATING", "label": label, "channels": []}
    snap = parse_snapshot(state, NOW, default_extract)
    assert [r.name for r in snap.rooms] == [family, persian, "soft\u00adhyphen"]


@pytest.mark.parametrize(
    "label",
    ["bad\ud800", "a\u2028b", "a\u2029b", "a\x85b", "a\x00b", "a\u202eb", "a\u2066b", "a\u2069b"],
)
def test_surrogates_line_separators_and_bidi_controls_are_replaced(
    label: str, default_extract: ExtractConfig
) -> None:
    state = make_state()
    state["groups"]["G1"]["label"] = label
    name = parse_snapshot(state, NOW, default_extract).rooms[0].name
    assert len(name) == len(label)
    assert name[1] == " " or name.startswith("bad ")
    name.encode("utf-8")  # a lone surrogate would raise here (and break the exposition)


def test_describing_a_huge_payload_is_bounded(default_extract: ExtractConfig) -> None:
    raw = {f"k{i}": 1 for i in range(1_000_000)}
    start = time.perf_counter()
    with pytest.raises(UpstreamError):
        parse_snapshot(raw, NOW, default_extract)
    assert time.perf_counter() - start < 1.0
