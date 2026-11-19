"""Pure series computation: contract dataclasses plus metric definitions to label/value maps."""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from homematic_exporter.contracts import BatteryRecord, Contact, Device, Room, Snapshot, Valve
from homematic_exporter.metrics.schema import (
    EXTRAS_PREFIX,
    LABEL_ATTRS,
    MetricDef,
    Transform,
)
from homematic_exporter.metrics.text import clean_text

LabelValues = tuple[str, ...]
__all__ = ["LABEL_ATTRS", "LabelValues", "SeriesSet", "compute_series", "to_value"]


@dataclass(frozen=True, slots=True)
class SeriesSet:
    """The series of one metric: sorted label-value tuples with values."""

    samples: tuple[tuple[LabelValues, float], ...]
    entities: int  # how many entities of the scope were considered
    duplicates: int  # entities dropped because an earlier one had the same label values


Entity = Room | Device | Valve | Contact | BatteryRecord


def _entities(
    scope: str, snapshot: Snapshot, batteries: Sequence[BatteryRecord]
) -> Sequence[Entity]:
    match scope:
        case "rooms":
            return snapshot.rooms
        case "devices":
            return snapshot.devices
        case "valves":
            return snapshot.valves
        case "contacts":
            return snapshot.contacts
        case _:
            return batteries


def _same(raw: object, operand: object) -> bool:
    """Equality that never mixes bools with numbers or text with numbers."""
    if isinstance(raw, bool) or isinstance(operand, bool):
        return isinstance(raw, bool) and isinstance(operand, bool) and raw == operand
    if isinstance(raw, str) or isinstance(operand, str):
        return isinstance(raw, str) and isinstance(operand, str) and raw == operand
    return isinstance(raw, int | float) and isinstance(operand, int | float) and raw == operand


def _finite(number: float) -> float | None:
    return number if math.isfinite(number) else None


def _number(raw: object) -> float | None:
    if isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, int | float):
        try:
            return _finite(float(raw))
        except OverflowError:  # an int beyond the float range
            return None
    return None


def to_value(raw: object, transform: Transform, scale: float) -> float | None:
    """The exported number, or None when there must be no series (missing or unusable value)."""
    if raw is None:
        return None
    if transform.kind == "equals":
        return 1.0 if _same(raw, transform.equals) else 0.0
    if transform.kind == "in":
        return 1.0 if any(_same(raw, member) for member in transform.members) else 0.0
    number = _number(raw)
    if number is None:
        return None
    if transform.kind == "bool":
        if isinstance(raw, bool):
            return number
        return 0.0 if number == 0 else 1.0
    return _finite(number * scale)


def _raw_getter(value: str) -> Callable[[Entity], object]:
    if value.startswith(EXTRAS_PREFIX):
        key = value.removeprefix(EXTRAS_PREFIX)
        return lambda entity: getattr(entity, "extras", {}).get(key)
    return lambda entity: getattr(entity, value, None)


def compute_series(
    definition: MetricDef, snapshot: Snapshot, batteries: Sequence[BatteryRecord]
) -> SeriesSet:
    entities = _entities(definition.scope, snapshot, batteries)
    attrs = [LABEL_ATTRS[definition.scope][label] for label in definition.labels]
    get_raw = _raw_getter(definition.value)
    samples: dict[LabelValues, float] = {}
    duplicates = 0
    for entity in entities:
        value = to_value(get_raw(entity), definition.transform, definition.scale)
        if value is None:
            continue
        labels = tuple(clean_text(str(getattr(entity, attr))) for attr in attrs)
        if labels in samples:
            duplicates += 1
            continue
        samples[labels] = value
    return SeriesSet(tuple(sorted(samples.items())), len(entities), duplicates)
