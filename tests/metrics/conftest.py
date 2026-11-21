"""Module-local fixtures: a raw config dict (default extract/tuning) and a metric-entry helper."""

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.conftest import DEFAULT_CONFIG


def metric(**overrides: Any) -> dict[str, Any]:
    """One valid metric entry (room temperature); keyword arguments override single keys."""
    entry: dict[str, Any] = {
        "name": "homematic_room_temperature_celsius",
        "help": "Room temperature",
        "type": "gauge",
        "scope": "rooms",
        "value": "temperature_celsius",
        "labels": ["room"],
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def raw_config() -> dict[str, Any]:
    """The bundled default `extract`/`tuning` with an empty `metrics` list, as a mutable dict."""
    data: dict[str, Any] = yaml.safe_load(DEFAULT_CONFIG.read_text())
    out = copy.deepcopy(data)
    out["metrics"] = []
    return out


@pytest.fixture
def write_config(tmp_path: Path) -> Any:
    def _write(data: dict[str, Any] | str, name: str = "config.yaml") -> Path:
        path = tmp_path / name
        path.write_text(data if isinstance(data, str) else yaml.safe_dump(data))
        return path

    return _write
