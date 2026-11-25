"""Shared contracts between modules (spec section 3).

This file, `config_models.py` and `redact.py` are the only things modules may share. Changing any
of them requires a `specs/spec.md` change in the same commit, in its own small PR merged first.

Notes: the dataclasses are frozen but hold a mapping in `extras`, so they are not hashable; do not
put them in sets or use them as dict keys (key by name instead). The `Source` and `StateStore`
Protocols are `runtime_checkable`, but `isinstance` only checks that the method names exist, not
their signatures: rely on mypy for signature conformance.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

# Config-defined raw fields (extract.extras), keyed by the configured key.
Extras = Mapping[str, float | str | bool | None]


@dataclass(frozen=True, slots=True)
class Room:
    name: str
    temperature_celsius: float | None
    setpoint_celsius: float | None
    humidity: float | None  # raw source value (percent); scaled by the metric definition
    control_mode: str | None  # raw, e.g. "AUTOMATIC"
    window_state: str | None  # raw, e.g. "OPEN" | "TILTED" | "CLOSED"
    extras: Extras


@dataclass(frozen=True, slots=True)
class Device:
    name: str  # "<room> <device_type>", unique
    room: str  # the configured system room if not in exactly one room
    device_type: str  # from extract.device_models
    low_battery: bool | None
    unreachable: bool | None
    undervoltage: bool | None
    rssi_dbm: int | None
    extras: Extras


@dataclass(frozen=True, slots=True)
class Valve:
    room: str
    device_type: str  # from the extract.valves rule, e.g. "floor-valve"
    device: str  # "<room> floor-valve" or the radiator device name
    position_ratio: float | None
    actual_temperature_celsius: float | None  # where the rule maps it (radiators)
    extras: Extras


@dataclass(frozen=True, slots=True)
class Contact:
    room: str
    device_type: str
    device: str
    window_state: str | None  # raw
    extras: Extras


@dataclass(frozen=True, slots=True)
class Snapshot:
    taken_at: float  # unix seconds, UTC
    rooms: tuple[Room, ...]
    devices: tuple[Device, ...]
    valves: tuple[Valve, ...]
    contacts: tuple[Contact, ...]


@dataclass(frozen=True, slots=True)
class BatteryRecord:
    device: str
    room: str
    device_type: str
    low_since: float | None  # unix seconds
    last_replaced: float | None


class UpstreamError(Exception):
    """Failure talking to the upstream.

    `body` must already be scrubbed of credentials by the raiser.
    """

    def __init__(self, message: str, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


# How a source treats two devices with the same name in one room (spec C1): `error` raises
# NameCollisionError (the app uses it until the first successful poll, i.e. startup); `suffix`
# appends -2, -3 ordered by SGTIN and the source logs one WARNING per new collision (names only).
CollisionPolicy = Literal["error", "suffix"]


class NameCollisionError(Exception):
    """Two or more entities (devices, valves, contacts or rooms) would get the same name."""

    def __init__(self, names: Sequence[str]) -> None:
        super().__init__(f"name collision: {', '.join(sorted(names))}")
        self.names = tuple(sorted(names))


@runtime_checkable
class Source(Protocol):
    async def fetch(self, on_collision: CollisionPolicy = "error") -> Snapshot:
        """Return the current snapshot.

        Raises UpstreamError on upstream failure and NameCollisionError when `on_collision` is
        "error" and device names collide.
        """
        ...


@runtime_checkable
class StateStore(Protocol):
    def load(self, key: str) -> dict[str, object] | None: ...

    def save(self, key: str, value: dict[str, object]) -> None:
        """Persist atomically."""
        ...
