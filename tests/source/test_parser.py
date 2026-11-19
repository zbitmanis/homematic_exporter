import copy
import json
import logging
import math
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
from homematic_exporter.source.parser import parse_snapshot, parse_with_report

from .conftest import device, make_state

NOW = 1_795_000_000.0


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
            Device("kitchen wall-thermostat", "kitchen", "wall-thermostat", False, False, False, -60, {}),
            Device("bedroom temp-humidity-display", "bedroom", "temp-humidity-display", True, False, False, -70, {}),
            Device("bedroom radiator-thermostat", "bedroom", "radiator-thermostat", False, False, False, -55, {}),
            Device("hall temp-humidity-sensor", "hall", "temp-humidity-sensor", False, True, False, None, {}),
            Device("hall door-window-contact", "hall", "door-window-contact", False, False, False, -62, {}),
            Device("system floor-controller", "system", "floor-controller", False, False, False, -70, {}),
            Device("system circulation-pump-switch", "system", "circulation-pump-switch", None, False, False, -48, {}),
            Device("hall hmip-new-1", "hall", "hmip-new-1", False, False, False, -66, {}),
            Device("system access-point", "system", "access-point", None, False, False, None, {}),
            Device("bedroom door-window-contact", "bedroom", "door-window-contact", False, False, False, -58, {}),
        ),
        valves=(
            Valve("kitchen", "floor-valve", "kitchen floor-valve", 0.1, None, {}),
            Valve("hall", "floor-valve", "hall floor-valve", 0.0, None, {}),
            Valve("bedroom", "radiator-thermostat", "bedroom radiator-thermostat", 0.3, 20.1, {}),
        ),
        contacts=(
            Contact("hall", "door-window-contact", "hall door-window-contact", "CLOSED", {}),
            Contact("bedroom", "door-window-contact", "bedroom door-window-contact", "OPEN", {}),
        ),
    )  # fmt: skip


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
    state = make_state(
        F=device("HmIP-FALMOT-C12", lowBat=False)
    )
    state["devices"]["F"]["functionalChannels"].update(
        {
            "1": {"functionalChannelType": "FLOOR_TERMINAL_BLOCK_MECHANIC_CHANNEL", "groups": ["G1"], "valvePosition": 0.2},
            "2": {"functionalChannelType": "FLOOR_TERMINAL_BLOCK_MECHANIC_CHANNEL", "groups": ["G1"], "valvePosition": 0.4},
        }
    )  # fmt: skip
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
    assert next(v for v in snap.valves if v.device_type == "radiator-thermostat").position_ratio is None


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
    state = make_state(A=device(rssiDeviceValue=-60.0), B=device("HmIP-STHD", rssiDeviceValue=-60.5))
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
    state["groups"].update(
        {
            "X1": "str",
            "X2": None,
            "X3": {"type": "HEATING"},  # no label
            "X4": {"type": "HEATING", "label": ""},  # empty label
            "X5": {"type": "HEATING", "label": 7},
            "X6": {"type": "HEATING", "label": "ok", "channels": "nope"},
            "X7": {"type": "HEATING", "label": "ok2", "channels": [None, "x", {"deviceId": 3}, {}, {"deviceId": "A"}]},
            "X8": {"type": ["HEATING"], "label": "bad-type"},
        }
    )  # fmt: skip
    snap = parse_snapshot(state, NOW, default_extract)
    assert [r.name for r in snap.rooms] == ["lab", "ok", "ok2"]
    assert snap.devices[0].room == "system"  # in lab and ok2


def test_channel_groups_with_unknown_or_non_heating_groups_skip_the_valve(
    default_extract: ExtractConfig,
) -> None:
    state = make_state(F=device("HmIP-FALMOT-C12"))
    state["groups"]["B"] = {"id": "B", "type": "BOILER", "label": "boiler", "channels": []}
    chans = state["devices"]["F"]["functionalChannels"]
    ctype = "FLOOR_TERMINAL_BLOCK_MECHANIC_CHANNEL"
    chans["1"] = {"functionalChannelType": ctype, "groups": ["B", "missing", 3, None], "valvePosition": 1}
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


def test_huge_input_is_linear_enough(default_extract: ExtractConfig) -> None:
    devices = {f"D{i}": device("HmIP-STH", lowBat=False) for i in range(2000)}
    state = make_state(**devices)
    snap = parse_snapshot(state, NOW, default_extract, "suffix")
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


def test_result_is_json_free_of_identifiers(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    snap = parse_snapshot(mini_state, NOW, default_extract)
    text = json.dumps(repr(snap))
    assert "SGTIN" not in text
    assert "ID-0" not in text


def test_parser_logs_nothing_itself(
    collision_state: dict[str, Any],
    default_extract: ExtractConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        parse_snapshot(collision_state, NOW, default_extract, "suffix")
    assert caplog.records == []  # logging once per collision is the sources' job
