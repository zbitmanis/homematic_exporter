import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from homematic_exporter.config_models import ExtractConfig, Tuning

FIXTURES = Path(__file__).parent / "source" / "fixtures"
DEFAULT_CONFIG = Path(__file__).parent.parent / "config" / "default-config.yaml"


@pytest.fixture
def mini_state() -> dict[str, Any]:
    """Hand-written, scrubbed Homematic IP state (3 rooms, 10 devices). Never the real capture."""
    data: dict[str, Any] = json.loads((FIXTURES / "mini_state.json").read_text())
    return data


@pytest.fixture
def collision_state(mini_state: dict[str, Any]) -> dict[str, Any]:
    """mini_state plus a second kitchen wall thermostat (two devices named the same)."""
    state = copy.deepcopy(mini_state)
    twin = copy.deepcopy(state["devices"]["ID-0001"])
    twin.update(
        id="ID-0011", label="Wall Thermostat 2", serializedGlobalTradeItemNumber="SGTIN-0011"
    )
    state["devices"]["ID-0011"] = twin
    state["groups"]["ID-0201"]["channels"].append({"deviceId": "ID-0011", "channelIndex": 1})
    return state


def _default_config() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(DEFAULT_CONFIG.read_text())
    return data


@pytest.fixture
def default_extract() -> ExtractConfig:
    """The `extract` section of the bundled default config: the one copy all module tests share."""
    return ExtractConfig.model_validate(_default_config()["extract"])


@pytest.fixture
def default_tuning() -> Tuning:
    return Tuning.model_validate(_default_config()["tuning"])
