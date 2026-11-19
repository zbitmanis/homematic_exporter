"""Shared by both sources: parse a raw configuration and log what the parser noticed, once."""

import logging

from homematic_exporter.config_models import ExtractConfig
from homematic_exporter.contracts import CollisionPolicy, Snapshot
from homematic_exporter.redact import scrub
from homematic_exporter.source.parser import parse_with_report

logger = logging.getLogger("homematic_exporter.source")

_MAX_LOGGED_CHARS = 64
_MAX_SCRUBBED_INPUT = 4096
_MAX_LOGGED_COLLISIONS = 20
_MAX_REMEMBERED_MODELS = 256


def _printable(text: str) -> str:
    """Scrubbed, then bounded and escaped (no newlines): safe to put in a log line.

    Scrubbing first means a secret straddling the length cut is never logged in part.
    """
    return repr(scrub(text[:_MAX_SCRUBBED_INPUT])[:_MAX_LOGGED_CHARS])


class SnapshotBuilder:
    """Holds the per-source log state (not thread-safe: used from the event loop only)."""

    def __init__(self, extract: ExtractConfig) -> None:
        self._extract = extract
        self._collisions: frozenset[str] = frozenset()
        self._warned_models: set[str] = set()

    def build(self, raw: object, now: float, on_collision: CollisionPolicy) -> Snapshot:
        snapshot, report = parse_with_report(raw, now, self._extract, on_collision)
        current = frozenset(report.collisions)
        new = sorted(current - self._collisions)
        for name in new[:_MAX_LOGGED_COLLISIONS]:
            logger.warning("name collision, suffixing: %s", _printable(name))
        if len(new) > _MAX_LOGGED_COLLISIONS:
            logger.warning("name collision: %d more not listed", len(new) - _MAX_LOGGED_COLLISIONS)
        self._collisions = current
        for model in report.unmapped_models:
            if model in self._warned_models or len(self._warned_models) >= _MAX_REMEMBERED_MODELS:
                continue
            self._warned_models.add(model)
            logger.warning(
                "unmapped device model %s: using the lowercased model", _printable(model)
            )
        return snapshot
