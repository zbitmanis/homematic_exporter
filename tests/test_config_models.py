from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from homematic_exporter.config_models import (
    ContactRule,
    ExtractConfig,
    ExtraField,
    Tuning,
    ValveRule,
)

Mutation = Callable[[dict[str, Any]], object]


def minimal() -> dict[str, Any]:
    return {
        "device_models": {"HmIP-WTH-1": "wall-thermostat"},
        "rooms": {"temperature_celsius": "actualTemperature"},
        "device_flags": {"low_battery": "lowBat"},
        "valves": [],
        "contacts": [],
    }


VALVE = {
    "channel_type": "X",
    "device_type": "floor-valve",
    "room_from": "channel_groups",
    "fields": {"position_ratio": "valvePosition"},
}


def test_defaults() -> None:
    cfg = ExtractConfig.model_validate(minimal())
    assert cfg.system_room == "system" and cfg.room_group_type == "HEATING" and cfg.extras == []
    tuning = Tuning()
    assert tuning.heat_demand_min_position == 0.0 and tuning.state_retention_days == 90


def test_valve_and_contact_rules() -> None:
    data = minimal()
    data["valves"] = [VALVE]
    data["contacts"] = [{"channel_type": "Y", "fields": {"window_state": "windowState"}}]
    cfg = ExtractConfig.model_validate(data)
    assert isinstance(cfg.valves[0], ValveRule) and isinstance(cfg.contacts[0], ContactRule)


def _error_locations(data: dict[str, Any]) -> list[tuple[Any, ...]]:
    with pytest.raises(ValidationError) as info:
        ExtractConfig.model_validate(data)
    return [tuple(e["loc"]) for e in info.value.errors()]


@pytest.mark.parametrize(
    ("what", "mutate", "expected_loc"),
    [
        ("unknown top-level key", lambda d: d.update(bogus=1), ("bogus",)),
        ("unknown room attribute", lambda d: d["rooms"].update(sgtin="x"), ("rooms",)),
        ("unknown device flag", lambda d: d["device_flags"].update(serial="x"), ("device_flags",)),
        (
            "bad room_from",
            lambda d: d["valves"].append({**VALVE, "room_from": "nowhere"}),
            ("valves", 0, "room_from"),
        ),
        (
            "unknown valve field",
            lambda d: d["valves"].append(
                {**VALVE, "fields": {"position_ratio": "p", "bogus": "y"}}
            ),
            ("valves", 0, "fields"),
        ),
        (
            "valve rule without position_ratio",
            lambda d: d["valves"].append({**VALVE, "fields": {}}),
            ("valves", 0, "fields"),
        ),
        (
            "contact rule without window_state",
            lambda d: d["contacts"].append({"channel_type": "Y", "fields": {}}),
            ("contacts", 0, "fields"),
        ),
        (
            "unknown contact field",
            lambda d: d["contacts"].append({"channel_type": "Y", "fields": {"bogus": "y"}}),
            ("contacts", 0, "fields"),
        ),
        (
            "bad extras scope",
            lambda d: d.update(extras=[{"scope": "galaxy", "key": "k", "field": "f"}]),
            ("extras", 0, "scope"),
        ),
        (
            "bad extras key",
            lambda d: d.update(extras=[{"scope": "room", "key": "Bad-Key", "field": "f"}]),
            ("extras", 0, "key"),
        ),
        (
            "duplicate extras entry",
            lambda d: d.update(
                extras=[
                    {"scope": "room", "key": "k", "field": "a"},
                    {"scope": "room", "key": "k", "field": "b"},
                ]
            ),
            ("extras",),
        ),
        ("missing required section", lambda d: d.pop("device_models"), ("device_models",)),
    ],
)
def test_invalid_config_is_rejected_with_the_key_path(
    what: str, mutate: Mutation, expected_loc: tuple[Any, ...]
) -> None:
    data = minimal()
    mutate(data)
    assert expected_loc in _error_locations(data), what


def test_same_extras_key_in_different_scopes_is_allowed() -> None:
    data = minimal()
    data["extras"] = [
        {"scope": "room", "key": "k", "field": "a"},
        {"scope": "device", "key": "k", "field": "a"},
    ]
    assert len(ExtractConfig.model_validate(data).extras) == 2


def test_extras_field() -> None:
    data = minimal()
    data["extras"] = [{"scope": "room", "key": "boost_duration", "field": "boostDuration"}]
    assert ExtractConfig.model_validate(data).extras[0] == ExtraField(
        scope="room", key="boost_duration", field="boostDuration"
    )


def test_tuning_rejects_bad_values() -> None:
    with pytest.raises(ValidationError):
        Tuning(heat_demand_min_position=-0.1)
    with pytest.raises(ValidationError):
        Tuning(state_retention_days=0)
    with pytest.raises(ValidationError):
        Tuning.model_validate({"bogus": 1})


@pytest.mark.parametrize("days", [36501, 10**30])
def test_state_retention_days_has_an_upper_bound(days: int) -> None:
    with pytest.raises(ValidationError):
        Tuning(state_retention_days=days)


def test_state_retention_days_accepts_the_upper_bound() -> None:
    assert Tuning(state_retention_days=36500).state_retention_days == 36500
