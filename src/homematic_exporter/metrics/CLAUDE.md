# metrics/ module

Plan: `specs/plans/metrics.md`. Owns the `config.yaml` schema (pydantic v2, `extra=forbid`), config loading and validation (spec R19-R21), and **all** Prometheus metrics: entity, derived (6.5) and meta (6.6) ones. Imports nothing from other modules (only `contracts`, `config_models`, `redact`). The `check_config` command is NOT here (task 4, spec R20).

Interface (spec 3):
- `load_config(path: Path | None = None) -> AppConfig`: `AppConfig` composes `Tuning`, `ExtractConfig` and the metric definitions. An explicit `path` must exist; `None` means mount path, then the bundled default. Never reads the environment (`app` passes `CONFIG_FILE`).
- `Registry.build(metric_defs, tuning)`, `Registry.update(snapshot, batteries)`, `Registry.record_success(timestamp, duration)`, `Registry.record_error()`, `Registry.exposition() -> bytes`, `render(config, snapshot, batteries=()) -> bytes`.

Rules:
- Use a private `CollectorRegistry`, never the global one. `yaml.safe_load` only.
- Each YAML entry: `scope`, `value`, `labels`, `scale`, `transform` (spec 6.1). Reject names that break `homematic_<thing>_<unit>` or labels outside `room`, `device_type`, `device` (mapping table in 6.1).
- `homematic_data_age_seconds` comes from a custom collector: no series until the first `record_success` (`Gauge.set_function` cannot do that). `homematic_exporter_build_info` takes `version` from the `APP_VERSION` value the caller provides.
- Missing source values remove the series instead of exporting stale numbers; log a warning for a metric with zero series on two consecutive updates (C11).
- Battery metrics read `BatteryRecord`; history itself lives in `state`.
- Tests: every R19 error class with its key path; golden exposition text from a **hand-built `Snapshot`** (not the fixture-through-parser path, which is task 4); extras added by config only; config resolution order; no secrets in errors.
