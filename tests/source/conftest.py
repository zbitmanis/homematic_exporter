import copy
from typing import Any

import pytest

from homematic_exporter.config_models import ExtractConfig


@pytest.fixture
def extract_with_extras(default_extract: ExtractConfig) -> ExtractConfig:
    """The default extract plus one extra per scope (shared fixture is never edited)."""
    data = default_extract.model_dump()
    data["extras"] = [
        {"scope": "room", "key": "boost_duration", "field": "boostDuration"},
        {"scope": "device", "key": "rssi_peer", "field": "rssiPeerValue"},
        {"scope": "valve", "key": "valve_state", "field": "valveState"},
        {"scope": "contact", "key": "sabotage", "field": "sabotage"},
    ]
    return ExtractConfig.model_validate(data)


def make_state(**devices: dict[str, Any]) -> dict[str, Any]:
    """A tiny raw state with one HEATING room 'lab' (group G1) and the given devices."""
    state: dict[str, Any] = {
        "devices": {},
        "groups": {
            "G1": {"id": "G1", "type": "HEATING", "label": "lab", "channels": []},
        },
    }
    for dev_id, dev in devices.items():
        full = copy.deepcopy(dev)
        full.setdefault("id", dev_id)
        full.setdefault("serializedGlobalTradeItemNumber", f"SG-{dev_id}")
        state["devices"][dev_id] = full
        state["groups"]["G1"]["channels"].append({"deviceId": dev_id, "channelIndex": 0})
    return state


def device(model: str = "HmIP-STH", **base: Any) -> dict[str, Any]:
    return {
        "modelType": model,
        "functionalChannels": {"0": {"functionalChannelType": "DEVICE_BASE", **base}},
    }
