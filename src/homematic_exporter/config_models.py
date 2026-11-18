"""Shared, validated config models for the `extract` and `tuning` sections of config.yaml.

See spec 5.1. Shared contract like `contracts.py`: `source` and `state` consume these types, `metrics` owns
loading and the metric-definition schema. Unknown keys are rejected (spec R19).
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOM_ATTRIBUTES = frozenset(
    {"temperature_celsius", "setpoint_celsius", "humidity", "control_mode", "window_state"}
)
DEVICE_FLAGS = frozenset({"low_battery", "unreachable", "undervoltage", "rssi_dbm"})
VALVE_FIELDS = frozenset({"position_ratio", "actual_temperature_celsius"})
CONTACT_FIELDS = frozenset({"window_state"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _only(fields: dict[str, str], allowed: frozenset[str], what: str) -> None:
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise ValueError(f"unknown {what} attribute(s) {unknown}; allowed: {sorted(allowed)}")


class ValveRule(_Strict):
    channel_type: str
    device_type: str
    room_from: Literal["channel_groups", "device_room"]
    fields: dict[str, str]

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        _only(self.fields, VALVE_FIELDS, "valve")
        return self


class ContactRule(_Strict):
    channel_type: str
    fields: dict[str, str]

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        _only(self.fields, CONTACT_FIELDS, "contact")
        return self


class ExtraField(_Strict):
    scope: Literal["room", "device", "valve", "contact"]
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    field: str


class ExtractConfig(_Strict):
    system_room: str = "system"
    room_group_type: str = "HEATING"
    device_models: dict[str, str]
    rooms: dict[str, str]
    device_flags: dict[str, str]
    valves: list[ValveRule]
    contacts: list[ContactRule]
    extras: list[ExtraField] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        _only(self.rooms, ROOM_ATTRIBUTES, "room")
        _only(self.device_flags, DEVICE_FLAGS, "device flag")
        return self


class Tuning(_Strict):
    heat_demand_min_position: float = Field(default=0.0, ge=0.0, le=1.0)
    state_retention_days: int = Field(default=90, ge=1)
