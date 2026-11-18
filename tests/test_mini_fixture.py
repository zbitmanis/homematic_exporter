"""The mini fixture must stay structurally consistent and free of identifying data."""

import json
import re
from typing import Any

from tests.conftest import FIXTURES

REAL_SGTIN = re.compile(r"\b[0-9A-F]{24}\b")
REAL_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")


def test_shape(mini_state: dict[str, Any]) -> None:
    assert set(mini_state) == {"home", "devices", "groups"}
    rooms = [g for g in mini_state["groups"].values() if g["type"] == "HEATING"]
    assert {g["label"] for g in rooms} == {"kitchen", "bedroom", "hall"}
    assert len(mini_state["devices"]) == 8


def test_references_are_consistent(mini_state: dict[str, Any]) -> None:
    devices, groups = mini_state["devices"], mini_state["groups"]
    for group in groups.values():
        for ch in group["channels"]:
            assert ch["deviceId"] in devices
            assert str(ch["channelIndex"]) in devices[ch["deviceId"]]["functionalChannels"]
    for dev in devices.values():
        for ch in dev["functionalChannels"].values():
            for gid in ch["groups"]:
                assert gid in groups


def test_covers_the_cases_the_spec_needs(mini_state: dict[str, Any]) -> None:
    devices = list(mini_state["devices"].values())
    flat = [c for d in devices for c in d["functionalChannels"].values()]
    assert any(c.get("lowBat") is True for c in flat)  # low battery
    assert any(c.get("unreach") is True for c in flat)  # unreachable device
    assert any(c.get("actualTemperature") is None and "humidity" in c for c in flat)  # None values
    assert any(c.get("functionalChannelType") == "SHUTTER_CONTACT_CHANNEL" for c in flat)
    floor = [
        c for c in flat if c.get("functionalChannelType") == "FLOOR_TERMINAL_BLOCK_MECHANIC_CHANNEL"
    ]
    assert any(not c["groups"] for c in floor)  # unused floor channel
    assert any(len(set(c["groups"])) == 1 for c in floor)  # channel with a room
    assert any(d["modelType"] == "HmIP-NEW-1" for d in devices)  # unmapped model


def test_fixture_is_scrubbed() -> None:
    text = (FIXTURES / "mini_state.json").read_text()
    json.loads(text)
    assert not REAL_SGTIN.search(text)
    assert not REAL_UUID.search(text)
    assert "token" not in text.lower()
