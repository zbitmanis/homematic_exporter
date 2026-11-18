import pytest
from pydantic import ValidationError

from homematic_exporter.config_models import (
    ContactRule,
    ExtractConfig,
    ExtraField,
    Tuning,
    ValveRule,
)


def minimal() -> dict:  # type: ignore[type-arg]
    return {
        "device_models": {"HmIP-WTH-1": "wall-thermostat"},
        "rooms": {"temperature_celsius": "actualTemperature"},
        "device_flags": {"low_battery": "lowBat"},
        "valves": [],
        "contacts": [],
    }


def test_defaults() -> None:
    cfg = ExtractConfig.model_validate(minimal())
    assert cfg.system_room == "system" and cfg.room_group_type == "HEATING" and cfg.extras == []
    tuning = Tuning()
    assert tuning.heat_demand_min_position == 0.0 and tuning.state_retention_days == 90


def test_valve_and_contact_rules() -> None:
    data = minimal()
    data["valves"] = [
        {
            "channel_type": "X",
            "device_type": "floor-valve",
            "room_from": "channel_groups",
            "fields": {"position_ratio": "valvePosition"},
        }
    ]
    data["contacts"] = [{"channel_type": "Y", "fields": {"window_state": "windowState"}}]
    cfg = ExtractConfig.model_validate(data)
    assert isinstance(cfg.valves[0], ValveRule) and isinstance(cfg.contacts[0], ContactRule)


@pytest.mark.parametrize(
    ("path", "mutate"),
    [
        ("unknown top-level key", lambda d: d.update(bogus=1)),
        ("unknown room attribute", lambda d: d["rooms"].update(sgtin="serialNumber")),
        ("unknown device flag", lambda d: d["device_flags"].update(serial="x")),
        (
            "bad room_from",
            lambda d: d["valves"].append(
                {"channel_type": "X", "device_type": "v", "room_from": "nowhere", "fields": {}}
            ),
        ),
        (
            "unknown valve field",
            lambda d: d["valves"].append(
                {
                    "channel_type": "X",
                    "device_type": "v",
                    "room_from": "device_room",
                    "fields": {"bogus": "y"},
                }
            ),
        ),
        (
            "unknown contact field",
            lambda d: d["contacts"].append({"channel_type": "Y", "fields": {"bogus": "y"}}),
        ),
        (
            "bad extras scope",
            lambda d: d.update(extras=[{"scope": "galaxy", "key": "k", "field": "f"}]),
        ),
    ],
)
def test_invalid_config_is_rejected(path: str, mutate) -> None:  # type: ignore[no-untyped-def]
    data = minimal()
    mutate(data)
    with pytest.raises(ValidationError):
        ExtractConfig.model_validate(data)


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
