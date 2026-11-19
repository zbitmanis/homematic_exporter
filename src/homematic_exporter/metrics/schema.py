"""Metric definition schema (spec 6.1) and its semantic validation (spec R19).

`MetricDef` is purely structural (types and sizes, `extra=forbid`). Everything that needs context
(name rules, labels per scope, value attributes, extras references, uniqueness) lives in
`validate_metrics`, so each problem carries the exact key path (`metrics[3].labels[1]`).
"""

import dataclasses
import math
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Literal, NamedTuple, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from homematic_exporter.contracts import BatteryRecord, Contact, Device, Room, Valve
from homematic_exporter.metrics.text import NAME_PATTERN, escape_text, hide_tokens
from homematic_exporter.redact import scrub

Scope = Literal["rooms", "devices", "valves", "contacts", "batteries"]
Scalar = str | int | float | bool

MAX_METRICS = 500
MAX_NAME_LENGTH = 200
MAX_HELP_LENGTH = 500
MAX_TRANSFORM_MEMBERS = 64
MAX_ISSUES_SHOWN = 20
MAX_ECHO_LENGTH = 40
MAX_MESSAGE_LENGTH = 300

_EXTRAS_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
EXTRAS_PREFIX = "extras."

# Built-in metric families (spec 6.5, 6.6). Entity metrics may not reuse these names.
VALVES_OPEN = "homematic_valves_open"
HEAT_DEMAND = "homematic_heat_demand"
LAST_SUCCESS = "homematic_last_successful_poll_timestamp_seconds"
DATA_AGE = "homematic_data_age_seconds"
POLL_DURATION = "homematic_poll_duration_seconds"
POLL_ERRORS = "homematic_poll_errors"  # the counter is exposed as <name>_total
BUILD_INFO = "homematic_exporter_build_info"
RESERVED_NAMES = frozenset(
    {VALVES_OPEN, HEAT_DEMAND, LAST_SUCCESS, DATA_AGE, POLL_DURATION, POLL_ERRORS, BUILD_INFO}
)

# Spec 6.1 mapping table: labels available per metric scope and the matching `extras` scope.
_FULL_LABELS = {"room": "room", "device_type": "device_type", "device": "device"}
# Per scope: label name -> attribute of the entity that carries it. The single source for both
# validation (SCOPE_LABELS) and the registry.
LABEL_ATTRS: Mapping[str, Mapping[str, str]] = {
    "rooms": {"room": "name"},
    "devices": {**_FULL_LABELS, "device": "name"},
    "valves": _FULL_LABELS,
    "contacts": _FULL_LABELS,
    "batteries": _FULL_LABELS,
}
SCOPE_LABELS: Mapping[str, tuple[str, ...]] = {s: tuple(m) for s, m in LABEL_ATTRS.items()}
ALLOWED_LABELS = frozenset(_FULL_LABELS)
EXTRAS_SCOPE: Mapping[str, str] = {
    "rooms": "room",
    "devices": "device",
    "valves": "valve",
    "contacts": "contact",
}


def _values(cls: type, excluded: Iterable[str]) -> frozenset[str]:
    return frozenset(f.name for f in dataclasses.fields(cls)) - frozenset(excluded) - {"extras"}


# Value attributes are the contract dataclass fields that are not labels (derived, so a new
# attribute in `contracts.py` needs no change here).
SCOPE_VALUES: Mapping[str, frozenset[str]] = {
    "rooms": _values(Room, {"name"}),
    "devices": _values(Device, {"name", "room", "device_type"}),
    "valves": _values(Valve, {"room", "device_type", "device"}),
    "contacts": _values(Contact, {"room", "device_type", "device"}),
    "batteries": _values(BatteryRecord, {"room", "device_type", "device"}),
}


class Issue(NamedTuple):
    path: str  # config key path such as `metrics[3].labels[1]`; empty for file-level problems
    message: str


def make_issue(path: str, message: str) -> Issue:
    """An issue with secret-looking text scrubbed and overlong text cut (no secret values)."""
    return Issue(
        scrub(hide_tokens(escape_text(path))),
        scrub(hide_tokens(escape_text(message[:MAX_MESSAGE_LENGTH]))),
    )


def quote(value: object) -> str:
    """Repr of a value, cut to a short length so errors never echo big or hostile input."""
    try:
        text = repr(value)
    except ValueError:  # an integer beyond Python's digit limit
        text = "<unprintable value>"
    if len(text) > MAX_ECHO_LENGTH:
        closing = text[0] if text[0] in "'\"" else ""
        text = text[: MAX_ECHO_LENGTH - 3] + "..." + closing
    return hide_tokens(text)


class ConfigError(Exception):
    """Invalid configuration. `issues` hold the first few key paths with scrubbed messages (no
    secret values); `total` is the true number of problems.
    """

    def __init__(
        self, issues: Sequence[Issue], source: str | None = None, total: int | None = None
    ) -> None:
        # Cut before scrubbing: a hostile file may produce thousands of issues.
        self.total = len(issues) if total is None else total
        self.issues = tuple(make_issue(i.path, i.message) for i in issues[:MAX_ISSUES_SHOWN])
        self.source = source
        lines = [f"{i.path}: {i.message}" if i.path else i.message for i in self.issues]
        if self.total > MAX_ISSUES_SHOWN:
            lines.append(f"... and {self.total - MAX_ISSUES_SHOWN} more")
        header = f"invalid config {source}:" if source else "invalid config:"
        super().__init__("\n  ".join([header, *lines]))


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Transform(_Strict):
    """How a raw value becomes a number: none | bool | {equals: X} | {in: [A, B]} (spec 6.1)."""

    kind: Literal["none", "bool", "equals", "in"] = "none"
    equals: Scalar | None = None
    members: tuple[Scalar, ...] = Field(default=(), max_length=MAX_TRANSFORM_MEMBERS)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.kind == "equals" and self.equals is None:
            raise ValueError("equals needs a value")
        if self.kind == "in" and not self.members:
            raise ValueError("in needs a non-empty list")
        operands = [self.equals] if self.kind == "equals" else list(self.members)
        if any(isinstance(o, float) and not math.isfinite(o) for o in operands):
            raise ValueError("operands must be finite")
        return self


def _transform_from_yaml(raw: object) -> object:
    if isinstance(raw, Transform):
        return raw
    if isinstance(raw, str) and raw in ("none", "bool"):
        return {"kind": raw}
    if isinstance(raw, dict) and len(raw) == 1:
        ((key, operand),) = raw.items()
        if key == "equals":
            return {"kind": "equals", "equals": operand}
        if key == "in":
            return {"kind": "in", "members": operand}
    raise ValueError("expected none, bool, {equals: X} or {in: [A, B]}")


class MetricDef(_Strict):
    name: str = Field(max_length=MAX_NAME_LENGTH)
    help: str = Field(min_length=1, max_length=MAX_HELP_LENGTH)
    type: Literal["gauge"]
    scope: Scope
    value: str = Field(max_length=MAX_NAME_LENGTH)
    labels: tuple[str, ...] = Field(default=(), max_length=len(ALLOWED_LABELS))
    scale: float = Field(default=1.0, strict=True, allow_inf_nan=False)
    transform: Transform = Field(default_factory=Transform)

    @field_validator("transform", mode="before")
    @classmethod
    def _parse_transform(cls, raw: object) -> object:
        return _transform_from_yaml(raw)


def _name_issues(defs: Sequence[MetricDef]) -> list[Issue]:
    issues: list[Issue] = []
    first_seen: dict[str, int] = {}
    for i, d in enumerate(defs):
        path = f"metrics[{i}].name"
        if not NAME_PATTERN.fullmatch(d.name):
            issues.append(
                Issue(
                    path,
                    f"invalid name {quote(d.name)}: must be homematic_<thing>_<unit>"
                    " (lowercase letters, digits, single underscores)",
                )
            )
        elif d.name in RESERVED_NAMES:
            issues.append(Issue(path, f"name {quote(d.name)} is reserved for a built-in metric"))
        elif d.name.endswith("_total"):
            issues.append(Issue(path, "gauge names must not end in '_total' (counters only)"))
        elif d.name in first_seen:
            issues.append(
                Issue(
                    path,
                    f"duplicate metric name {quote(d.name)} (first defined at"
                    f" metrics[{first_seen[d.name]}])",
                )
            )
        first_seen.setdefault(d.name, i)
    return issues


def _label_issues(i: int, d: MetricDef) -> list[Issue]:
    issues: list[Issue] = []
    available = SCOPE_LABELS[d.scope]
    for j, label in enumerate(d.labels):
        path = f"metrics[{i}].labels[{j}]"
        if label not in ALLOWED_LABELS:
            allowed = ", ".join(sorted(ALLOWED_LABELS))
            issues.append(Issue(path, f"unknown label {quote(label)}; allowed: {allowed}"))
        elif label not in available:
            issues.append(
                Issue(
                    path,
                    f"label {quote(label)} is not available for scope {quote(d.scope)};"
                    f" available: {', '.join(available)}",
                )
            )
        elif label in d.labels[:j]:
            issues.append(Issue(path, f"duplicate label {quote(label)}"))
    return issues


def _scale_issue(i: int, d: MetricDef) -> Issue | None:
    if d.scale != 1.0 and d.transform.kind != "none":
        return Issue(f"metrics[{i}].scale", "only applies with transform 'none'")
    return None


def _value_issue(i: int, d: MetricDef, extras: Collection[tuple[str, str]] | None) -> Issue | None:
    path = f"metrics[{i}].value"
    if d.value in SCOPE_VALUES[d.scope]:
        return None
    key = d.value.removeprefix(EXTRAS_PREFIX)
    if key != d.value and d.scope in EXTRAS_SCOPE and _EXTRAS_KEY.fullmatch(key):
        if extras is None or (EXTRAS_SCOPE[d.scope], key) in extras:
            return None
        return Issue(
            path,
            f"no extract.extras entry with scope {quote(EXTRAS_SCOPE[d.scope])} and key"
            f" {quote(key)}",
        )
    allowed = ", ".join(sorted(SCOPE_VALUES[d.scope]))
    extra_hint = "" if d.scope not in EXTRAS_SCOPE else ", extras.<key>"
    return Issue(
        path,
        f"unknown value {quote(d.value)} for scope {quote(d.scope)};"
        f" allowed: {allowed}{extra_hint}",
    )


def validate_metrics(
    defs: Sequence[MetricDef], extras: Collection[tuple[str, str]] | None = None
) -> list[Issue]:
    """Semantic checks (R19). `extras` holds the `(scope, key)` pairs of `extract.extras`; with
    `None` the extras reference is checked for shape only (the registry has no extract section).
    """
    issues = _name_issues(defs)
    for i, d in enumerate(defs):
        issues.extend(_label_issues(i, d))
        for issue in (_value_issue(i, d, extras), _scale_issue(i, d)):
            if issue is not None:
                issues.append(issue)
    return issues
