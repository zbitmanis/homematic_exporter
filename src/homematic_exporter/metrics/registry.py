"""Prometheus registry for all exporter metrics (spec 3, 6, R6-R10, C11).

One private `CollectorRegistry` with one collector. `update` computes every series first and then
swaps one immutable state under a lock, so a concurrent scrape sees either the old or the new
snapshot, never a mix, and a series that is no longer produced disappears (R8). The module reads
neither the environment nor the clock except through the injected `clock` (scrape-time data age).
"""

import logging
import math
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric
from prometheus_client.registry import Collector

from homematic_exporter.config_models import Tuning
from homematic_exporter.contracts import BatteryRecord, Snapshot
from homematic_exporter.metrics.config import AppConfig
from homematic_exporter.metrics.schema import (
    BUILD_INFO,
    DATA_AGE,
    HEAT_DEMAND,
    LAST_SUCCESS,
    POLL_DURATION,
    POLL_ERRORS,
    VALVES_OPEN,
    ConfigError,
    MetricDef,
    validate_metrics,
)
from homematic_exporter.metrics.series import LabelValues, SeriesSet, compute_series

logger = logging.getLogger(__name__)

MAX_VERSION_LENGTH = 100
MIN_TIMESTAMP = 0.0
MAX_TIMESTAMP = 4102444800.0  # 2100-01-01, same bound as the state module
ZERO_SERIES_WARN_AFTER = 2  # consecutive updates with no series (C11)


@dataclass(frozen=True, slots=True)
class _Family:
    name: str
    help: str
    label_names: tuple[str, ...]
    samples: tuple[tuple[LabelValues, float], ...]


@dataclass(frozen=True, slots=True)
class _State:
    """Everything one scrape needs; replaced as a whole, never mutated."""

    families: tuple[_Family, ...] = ()
    poll_errors: int = 0
    last_success: float | None = None
    poll_duration: float | None = None


class _Collector(Collector):
    def __init__(self, get_state: Callable[[], _State], version: str, clock: Callable[[], float]):
        self._get_state = get_state
        self._version = version
        self._clock = clock

    def collect(self) -> Iterator[Metric]:
        state = self._get_state()
        for family in state.families:
            gauge = GaugeMetricFamily(family.name, family.help, labels=family.label_names)
            for labels, value in family.samples:
                gauge.add_metric(list(labels), value)
            yield gauge
        yield from self._meta(state)

    def _meta(self, state: _State) -> Iterator[Metric]:
        errors = CounterMetricFamily(POLL_ERRORS, "Failed polls", value=float(state.poll_errors))
        yield errors
        info = GaugeMetricFamily(BUILD_INFO, "Build information", labels=["version"])
        info.add_metric([self._version], 1.0)
        yield info
        if state.last_success is None or state.poll_duration is None:
            return
        yield _gauge(LAST_SUCCESS, "Unix time of the last successful poll", state.last_success)
        yield _gauge(POLL_DURATION, "Duration of the last poll", state.poll_duration)
        age = max(0.0, self._clock() - state.last_success)
        yield _gauge(DATA_AGE, "Seconds since the last successful poll", age)


def _gauge(name: str, help_text: str, value: float) -> GaugeMetricFamily:
    gauge = GaugeMetricFamily(name, help_text)
    gauge.add_metric([], value)
    return gauge


def _is_open(position: float | None, threshold: float) -> bool:
    return position is not None and math.isfinite(position) and position > threshold


class Registry:
    """Owns the metric definitions and the exposition. Use `Registry.build`."""

    def __init__(
        self,
        metric_defs: Sequence[MetricDef],
        tuning: Tuning,
        version: str,
        clock: Callable[[], float],
    ) -> None:
        self._defs = tuple(metric_defs)
        self._threshold = tuning.heat_demand_min_position
        self._lock = threading.Lock()
        self._state = _State()
        self._zero_streak: dict[str, int] = {}
        self._duplicates_warned: set[str] = set()
        self._first_update = True
        self._registry = CollectorRegistry()
        self._registry.register(_Collector(self._get_state, version[:MAX_VERSION_LENGTH], clock))

    @classmethod
    def build(
        cls,
        metric_defs: Sequence[MetricDef],
        tuning: Tuning,
        version: str = "dev",
        *,
        clock: Callable[[], float] = time.time,
    ) -> "Registry":
        """Validate the definitions (R19) and create an empty registry; `clock` is for tests."""
        if issues := validate_metrics(metric_defs):
            raise ConfigError(issues)
        return cls(metric_defs, tuning, version, clock)

    def _get_state(self) -> _State:
        with self._lock:
            return self._state

    def update(self, snapshot: Snapshot, batteries: Sequence[BatteryRecord] = ()) -> None:
        """Replace all entity and derived series from one snapshot (None values yield none)."""
        results = [(d, compute_series(d, snapshot, batteries)) for d in self._defs]
        families = [_Family(d.name, d.help, d.labels, r.samples) for d, r in results if r.samples]
        families.extend(self._derived(snapshot))
        with self._lock:
            self._track(results)
            self._state = _State(
                tuple(families),
                self._state.poll_errors,
                self._state.last_success,
                self._state.poll_duration,
            )
        if self._first_update:
            self._first_update = False
            count = sum(len(f.samples) for f in families)
            logger.info("metrics registry updated: %d series", count)

    def _derived(self, snapshot: Snapshot) -> list[_Family]:
        open_valves = sum(_is_open(v.position_ratio, self._threshold) for v in snapshot.valves)
        return [
            _Family(
                VALVES_OPEN,
                "Valves open above the heat demand threshold",
                (),
                (((), float(open_valves)),),
            ),
            _Family(
                HEAT_DEMAND,
                "1 if any valve is open (boiler demand proxy)",
                (),
                (((), 1.0 if open_valves else 0.0),),
            ),
        ]

    def _track(self, results: list[tuple[MetricDef, SeriesSet]]) -> None:
        """C11 and collision warnings; names only, never label values. Caller holds the lock."""
        for definition, result in results:
            name = definition.name
            if result.entities and not result.samples:
                streak = self._zero_streak.get(name, 0) + 1
                self._zero_streak[name] = streak
                if streak == ZERO_SERIES_WARN_AFTER:
                    logger.warning(
                        "metric %s has no series for %d consecutive updates;"
                        " check its value field and extract mapping",
                        name,
                        streak,
                    )
            else:
                self._zero_streak.pop(name, None)
            if result.duplicates and name not in self._duplicates_warned:
                self._duplicates_warned.add(name)
                logger.warning(
                    "metric %s: %d entities share the same label values; only the first is"
                    " exported (add labels)",
                    name,
                    result.duplicates,
                )
            elif not result.duplicates:
                self._duplicates_warned.discard(name)

    def record_success(self, timestamp: float, duration: float) -> None:
        """A poll succeeded at `timestamp` (unix seconds) and took `duration` seconds."""
        if not (math.isfinite(timestamp) and MIN_TIMESTAMP <= timestamp <= MAX_TIMESTAMP):
            raise ValueError("invalid timestamp")
        if not (math.isfinite(duration) and duration >= 0):
            raise ValueError("invalid duration")
        with self._lock:
            s = self._state
            self._state = _State(s.families, s.poll_errors, timestamp, duration)

    def record_error(self) -> None:
        with self._lock:
            s = self._state
            self._state = _State(s.families, s.poll_errors + 1, s.last_success, s.poll_duration)

    def exposition(self) -> bytes:
        """Prometheus text exposition of the current state (reads only memory)."""
        return generate_latest(self._registry)


def render(
    config: AppConfig,
    snapshot: Snapshot,
    batteries: Sequence[BatteryRecord] = (),
    version: str = "dev",
) -> bytes:
    """Build a registry, apply one snapshot, return the exposition (golden tests, check_config)."""
    registry = Registry.build(config.metrics, config.tuning, version)
    registry.update(snapshot, batteries)
    return registry.exposition()
