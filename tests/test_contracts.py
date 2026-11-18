import dataclasses
import inspect
from collections.abc import Mapping

import pytest

from homematic_exporter.contracts import (
    BatteryRecord,
    CollisionPolicy,
    Contact,
    Device,
    NameCollisionError,
    Room,
    Snapshot,
    Source,
    StateStore,
    UpstreamError,
    Valve,
)


def make_room() -> Room:
    return Room("kitchen", 21.3, 20.0, 50.0, "AUTOMATIC", None, {})


def make_device() -> Device:
    return Device(
        "kitchen wall-thermostat", "kitchen", "wall-thermostat", False, False, False, -60, {}
    )


def test_dataclasses_are_frozen_and_slotted() -> None:
    room = make_room()
    with pytest.raises(dataclasses.FrozenInstanceError):
        room.name = "other"  # type: ignore[misc]
    assert not hasattr(room, "__dict__")


def test_all_fields_present() -> None:
    names = {f.name for f in dataclasses.fields(Room)}
    assert names == {
        "name",
        "temperature_celsius",
        "setpoint_celsius",
        "humidity",
        "control_mode",
        "window_state",
        "extras",
    }
    assert {f.name for f in dataclasses.fields(Device)} == {
        "name",
        "room",
        "device_type",
        "low_battery",
        "unreachable",
        "undervoltage",
        "rssi_dbm",
        "extras",
    }
    assert {f.name for f in dataclasses.fields(Valve)} == {
        "room",
        "device_type",
        "device",
        "position_ratio",
        "actual_temperature_celsius",
        "extras",
    }
    assert {f.name for f in dataclasses.fields(Contact)} == {
        "room",
        "device_type",
        "device",
        "window_state",
        "extras",
    }
    assert {f.name for f in dataclasses.fields(BatteryRecord)} == {
        "device",
        "room",
        "device_type",
        "low_since",
        "last_replaced",
    }


def test_snapshot_holds_tuples() -> None:
    snap = Snapshot(
        taken_at=1.0, rooms=(make_room(),), devices=(make_device(),), valves=(), contacts=()
    )
    assert isinstance(snap.rooms, tuple) and snap.devices[0].room == "kitchen"


def test_extras_is_a_mapping() -> None:
    extras: Mapping[str, float | str | bool | None] = {
        "boost": 1.0,
        "mode": "x",
        "flag": True,
        "none": None,
    }
    assert Room("r", None, None, None, None, None, extras).extras["boost"] == 1.0


def test_upstream_error_carries_status_and_body() -> None:
    err = UpstreamError("poll failed", status=503, body="gateway timeout")
    assert err.status == 503 and err.body == "gateway timeout" and "poll failed" in str(err)
    assert UpstreamError("x").status is None


def test_protocols_are_runtime_checkable() -> None:
    class FakeSource:
        async def fetch(self, on_collision: CollisionPolicy = "error") -> Snapshot:
            return Snapshot(0.0, (), (), (), ())

    class FakeStore:
        def load(self, key: str) -> dict | None:  # type: ignore[type-arg]
            return None

        def save(self, key: str, value: dict) -> None:  # type: ignore[type-arg]
            return None

    assert isinstance(FakeSource(), Source)
    assert isinstance(FakeStore(), StateStore)
    assert not isinstance(object(), Source)


def test_source_fetch_is_a_coroutine_function() -> None:
    assert inspect.iscoroutinefunction(Source.fetch)
    assert not inspect.iscoroutinefunction(StateStore.load)


def test_field_types_are_none_tolerant() -> None:
    hints = {f.name: str(f.type) for f in dataclasses.fields(Device)}
    for name in ("low_battery", "unreachable", "undervoltage", "rssi_dbm"):
        assert "None" in hints[name]
    assert "None" in {f.name: str(f.type) for f in dataclasses.fields(Room)}["temperature_celsius"]


def test_entities_with_extras_are_not_hashable() -> None:
    with pytest.raises(TypeError):
        hash(make_room())


def test_name_collision_error_lists_sorted_names() -> None:
    err = NameCollisionError(["b room x", "a room x"])
    assert err.names == ("a room x", "b room x")
    assert "a room x, b room x" in str(err)
