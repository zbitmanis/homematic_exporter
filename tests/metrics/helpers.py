"""Shared builders for registry tests: hand-built snapshots and exposition parsing."""

from collections.abc import Mapping
from typing import Any

from prometheus_client.parser import text_string_to_metric_families

from homematic_exporter.contracts import Contact, Device, Room, Snapshot, Valve
from homematic_exporter.metrics import MetricDef

Series = dict[str, dict[tuple[tuple[str, str], ...], float]]


def defs(*entries: dict[str, Any]) -> list[MetricDef]:
    return [MetricDef.model_validate(e) for e in entries]


def room(name: str = "kitchen", **kw: Any) -> Room:
    base: dict[str, Any] = {
        "name": name,
        "temperature_celsius": 21.5,
        "setpoint_celsius": 22.0,
        "humidity": 55.0,
        "control_mode": "AUTOMATIC",
        "window_state": "CLOSED",
        "extras": {},
    }
    base.update(kw)
    return Room(**base)


def device(name: str = "kitchen wall-thermostat", room_name: str = "kitchen", **kw: Any) -> Device:
    base: dict[str, Any] = {
        "name": name,
        "room": room_name,
        "device_type": "wall-thermostat",
        "low_battery": False,
        "unreachable": False,
        "undervoltage": False,
        "rssi_dbm": -60,
        "extras": {},
    }
    base.update(kw)
    return Device(**base)


def valve(device_name: str = "kitchen floor-valve", position: float | None = 0.4, **kw: Any) -> Valve:
    base: dict[str, Any] = {
        "room": "kitchen",
        "device_type": "floor-valve",
        "device": device_name,
        "position_ratio": position,
        "actual_temperature_celsius": None,
        "extras": {},
    }
    base.update(kw)
    return Valve(**base)


def contact(**kw: Any) -> Contact:
    base: dict[str, Any] = {
        "room": "kitchen",
        "device_type": "door-window-contact",
        "device": "kitchen door-window-contact",
        "window_state": "CLOSED",
        "extras": {},
    }
    base.update(kw)
    return Contact(**base)


def snapshot(
    rooms: tuple[Room, ...] = (),
    devices: tuple[Device, ...] = (),
    valves: tuple[Valve, ...] = (),
    contacts: tuple[Contact, ...] = (),
) -> Snapshot:
    return Snapshot(1_700_000_000.0, rooms, devices, valves, contacts)


def parse(exposition: bytes) -> Series:
    """Sample name -> {sorted label items -> value}."""
    out: Series = {}
    for family in text_string_to_metric_families(exposition.decode()):
        for sample in family.samples:
            key = tuple(sorted(sample.labels.items()))
            out.setdefault(sample.name, {})[key] = sample.value
    return out


def only(series: Series, name: str) -> Mapping[tuple[tuple[str, str], ...], float]:
    return series.get(name, {})

