# metrics/ module

Plan: `specs/plans/metrics.md`. Owns the `config.yaml` schema (pydantic v2, `extra=forbid`), config loading and validation (spec R19-R21), and **all** Prometheus metrics: entity, derived (6.5) and meta (6.6) ones. Imports nothing from other modules (only `contracts`, `config_models`, `redact`). The `check_config` command is NOT here (task 4, spec R20).

Interface (spec 3):
- `load_config(path: Path | None = None) -> AppConfig`: `AppConfig` composes `Tuning`, `ExtractConfig` and the metric definitions. An explicit `path` must exist; `None` means mount path, then the bundled default. Never reads the environment (`app` passes `CONFIG_FILE`).
- `Registry.build(metric_defs, tuning, version="dev")`, `Registry.update(snapshot, batteries)`, `Registry.record_success(timestamp, duration)`, `Registry.record_error()`, `Registry.exposition() -> bytes`, `render(config, snapshot, batteries=(), version="dev") -> bytes`.

Rules:
- Use a private `CollectorRegistry`, never the global one. `yaml.safe_load` only.
- Each YAML entry: `scope`, `value`, `labels`, `scale`, `transform` (spec 6.1). Reject names that break `homematic_<thing>_<unit>` or labels outside `room`, `device_type`, `device` (mapping table in 6.1).
- `homematic_data_age_seconds` comes from a custom collector: no series until the first `record_success` (`Gauge.set_function` cannot do that). `homematic_exporter_build_info` takes its `version` label from the `version` argument (the caller, `app`, reads `APP_VERSION`; the metrics module never reads the environment).
- Missing source values remove the series instead of exporting stale numbers; log a warning for a metric with zero series on two consecutive updates (C11).
- Battery metrics read `BatteryRecord`; history itself lives in `state`.
- Tests: every R19 error class with its key path; golden exposition text from a **hand-built `Snapshot`** (not the fixture-through-parser path, which is task 4); extras added by config only; config resolution order; no secrets in errors.
- Allowed paths for this module are enforced by `.claude/ownership.yaml` (CI check and path-guard hook); anything else goes under "Requests" in your plan.

## Implementation notes (task 2b)
Files: `schema.py` (`MetricDef`, `Transform`, `validate_metrics`, `ConfigError`), `config.py` (`AppConfig`, `parse_config`, `load_config`), `series.py` (pure value/label computation), `registry.py` (`Registry`, `render`). Golden exposition: `tests/metrics/golden/default_config.prom` (regenerate with `PYTHONPATH=src:. python -m tests.metrics.test_default_config`, then review the diff).

Behaviour beyond the spec text (decisions):
- `parse_config(raw)` validates a parsed mapping; `load_config` adds resolution, file limits and YAML hygiene. Errors are `ConfigError` with `.issues` (`path`, `message`); every line goes through `redact.scrub` and echoed values are cut to 40 characters, so a secret-looking label or key never appears in an error. Only the first 20 issues are printed.
- `metrics` is a required key (empty list allowed); `tuning` may be omitted (defaults); `extract` is required.
- Resolution (R21): explicit path (must exist), else `/etc/homematic-exporter/config/config.yaml`, else `/app/default-config.yaml`, else the repo copy `config/default-config.yaml` (checkouts). A broken mounted file fails; it never falls back to the default. The chosen file is logged at INFO.
- `scale` applies to transform `none` only; any other transform with `scale != 1` is a config error (it would be silently ignored).
- `transform: bool` accepts a bool or a finite number (0 is 0, anything else 1); text is not guessed (`"false"` gives no series). `equals`/`in` never equal across bool, number and text (`True` is not `1`). `none` accepts finite numbers and bools; text gives no series. A result that is not finite (NaN, inf, scale overflow, an int beyond float range) gives no series.
- Two entities with the same label values in one metric (labels chosen too coarse) keep the first and log one warning per metric until it clears.
- C11: a metric warns at the second consecutive update with zero series only when its scope had entities (an empty scope such as no contacts is not a typo). Warnings name the metric, never label values. The first update logs the series count at INFO.
- `Registry` state is one immutable object swapped under a lock; an update computes everything first, so a scrape sees the old or the new snapshot, never a mix, and a failing update leaves the old state. Scrapes read memory only.
- Before the first `record_success` there is no `homematic_last_successful_poll_timestamp_seconds`, `homematic_poll_duration_seconds` or `homematic_data_age_seconds` series (a 0 would read as "polled in 1970"); the duration is only recorded for successes (`record_error` has no duration). Derived metrics (`homematic_valves_open`, `homematic_heat_demand`) exist from the first `update`. `homematic_poll_errors_total` and `homematic_exporter_build_info` exist from the start.
- `Registry.build(..., *, clock=time.time)`: the keyword-only `clock` exists for tests (data age at scrape time); `data_age` is clamped at 0 if the clock steps back. `version` is cut to 100 characters.
- Counters are exposed without a `_created` series (custom collector); entity metrics with no series produce no `# HELP`/`# TYPE` lines.

## Accepted limits
- YAML: file at most 1 MiB, valid UTF-8, one document, no aliases (rejected), no duplicate keys, no merge keys (`<<`), no non-string keys; nesting deeper than the interpreter's recursion limit is a `ConfigError`.
- At most 500 metric definitions, 64 `in` members, names 200 characters, help 500 characters. `state_retention_days` is capped at 36500 here because `config_models.Tuning` has no upper bound (see the plan's Requests).
- Value attributes of a scope are derived from the contract dataclasses, so a new field there becomes valid in config without a change here; `extras.<key>` is checked against `extract.extras` only when loading a whole config (`Registry.build` alone checks the shape).
- Only `gauge` entity metrics exist in v1. Series count is not capped; it is bounded by the snapshot, and metric definitions are operator-owned.
- Concurrency: `Registry` is safe for one writer plus any number of scrape readers (the poll task and the HTTP handlers, or threads). Several concurrent writers are serialised by the lock, but their warning bookkeeping assumes a single poll task.
- A raw-field typo still gives a missing series, not an error (C11); the warning and the series count log are the mitigation.
- Not verified here: coverage percentage (no coverage tool in the gate venv), behaviour against the real Homematic JSON (task 4 owns the fixture-through-parser golden).
