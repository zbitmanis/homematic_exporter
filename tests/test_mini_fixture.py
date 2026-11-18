"""The mini fixture must stay structurally consistent and free of identifying data."""

import json
import re
from typing import Any

from tests.conftest import FIXTURES

REAL_SGTIN = re.compile(r"\b[0-9A-F]{24}\b")
REAL_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


def _channels(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for d in state["devices"].values() for c in d["functionalChannels"].values()]


def check_references(state: dict[str, Any]) -> None:
    devices, groups = state["devices"], state["groups"]
    for group in groups.values():
        for ch in group["channels"]:
            assert ch["deviceId"] in devices
            assert str(ch["channelIndex"]) in devices[ch["deviceId"]]["functionalChannels"]
    for dev in devices.values():
        for ch in dev["functionalChannels"].values():
            for gid in ch["groups"]:
                assert gid in groups


def test_shape(mini_state: dict[str, Any]) -> None:
    assert set(mini_state) == {"home", "devices", "groups"}
    rooms = [g for g in mini_state["groups"].values() if g["type"] == "HEATING"]
    assert {g["label"] for g in rooms} == {"kitchen", "bedroom", "hall"}
    assert len(mini_state["devices"]) == 10


def test_references_are_consistent(mini_state: dict[str, Any]) -> None:
    check_references(mini_state)


def test_collision_variant_is_consistent_and_really_collides(
    collision_state: dict[str, Any],
) -> None:
    check_references(collision_state)
    kitchen = next(g for g in collision_state["groups"].values() if g.get("label") == "kitchen")
    kitchen_devices = {c["deviceId"] for c in kitchen["channels"]}
    models = [collision_state["devices"][d]["modelType"] for d in kitchen_devices]
    assert models.count("HmIP-WTH-1") == 2


def test_covers_the_cases_the_spec_needs(mini_state: dict[str, Any]) -> None:
    flat = _channels(mini_state)
    models = {d["modelType"] for d in mini_state["devices"].values()}
    assert any(c.get("lowBat") is True for c in flat)  # low battery
    assert any(c.get("unreach") is True for c in flat)  # unreachable device
    assert any(c.get("actualTemperature") is None and "humidity" in c for c in flat)  # None values
    assert {c.get("windowState") for c in flat if "windowState" in c} == {"CLOSED", "OPEN"}
    assert any(c.get("functionalChannelType") == "ACCESS_CONTROLLER_CHANNEL" for c in flat)
    floor = [
        c for c in flat if c.get("functionalChannelType") == "FLOOR_TERMINAL_BLOCK_MECHANIC_CHANNEL"
    ]
    assert any(not c["groups"] for c in floor)  # unused floor channel
    assert any(len(set(c["groups"])) == 1 for c in floor)  # channel with a room
    assert "HmIP-NEW-1" in models  # unmapped model
    assert any("boostDuration" in g for g in mini_state["groups"].values())  # extras example


def test_fixture_is_scrubbed() -> None:
    text = (FIXTURES / "mini_state.json").read_text()
    json.loads(text)
    assert not REAL_SGTIN.search(text)
    assert not REAL_UUID.search(text)
    assert "token" not in text.lower()
