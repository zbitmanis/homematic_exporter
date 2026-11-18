"""Shared, validated config models for the `extract` and `tuning` sections of config.yaml.

See spec 5.1. Shared contract like `contracts.py`: `source` and `state` consume these types,
`metrics` owns loading and the metric-definition schema. Unknown keys are rejected (spec R19).
The models are frozen (no attribute assignment), but the dicts and lists they hold are ordinary
mutable containers: treat them as read-only.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    @field_validator("fields")
    @classmethod
    def _check_fields(cls, fields: dict[str, str]) -> dict[str, str]:
        _only(fields, VALVE_FIELDS, "valve")
        if "position_ratio" not in fields:
            raise ValueError("a valve rule must map position_ratio")
        return fields


class ContactRule(_Strict):
    channel_type: str
    fields: dict[str, str]

    @field_validator("fields")
    @classmethod
    def _check_fields(cls, fields: dict[str, str]) -> dict[str, str]:
        _only(fields, CONTACT_FIELDS, "contact")
        if "window_state" not in fields:
            raise ValueError("a contact rule must map window_state")
        return fields


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

    @field_validator("rooms")
    @classmethod
    def _check_rooms(cls, rooms: dict[str, str]) -> dict[str, str]:
        _only(rooms, ROOM_ATTRIBUTES, "room")
        return rooms

    @field_validator("device_flags")
    @classmethod
    def _check_device_flags(cls, flags: dict[str, str]) -> dict[str, str]:
        _only(flags, DEVICE_FLAGS, "device flag")
        return flags

    @field_validator("extras")
    @classmethod
    def _check_extras(cls, extras: list[ExtraField]) -> list[ExtraField]:
        seen: set[tuple[str, str]] = set()
        for extra in extras:
            ident = (extra.scope, extra.key)
            if ident in seen:
                raise ValueError(
                    f"duplicate extras entry for scope {extra.scope!r}, key {extra.key!r}"
                )
            seen.add(ident)
        return extras


class Tuning(_Strict):
    heat_demand_min_position: float = Field(default=0.0, ge=0.0, le=1.0)
    state_retention_days: int = Field(default=90, ge=1)
