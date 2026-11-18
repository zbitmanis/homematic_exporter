# metrics/ module

Plan: `specs/plans/metrics.md`. Owns all metrics including derived and meta ones (`record_success`, `record_error`, `render`); the `check_config` command is NOT here (task 4, spec R20). Owns: the `config.yaml` schema (pydantic v2, `extra=forbid`), config loading/validation (spec R19-R21), the `check_config` command, and prometheus objects. Imports nothing from other modules.

- `Registry.build(config)` creates metrics from YAML (`yaml.safe_load` only, validated schema); `Registry.update(snapshot)` sets values. Use a private `CollectorRegistry`, not the global one.
- Each YAML entry: source field, metric name, type, labels, unit. Reject names that break `homematic_<thing>_<unit>` or labels outside `room`, `device_type`, `device`.
- Use `Gauge.set_function` for values computed at scrape time (e.g. data age).
- Missing source values remove the series rather than exporting stale numbers.
- Battery metrics (`homematic_device_low_battery`, `homematic_device_unreachable`, low-since and last-replaced timestamps) are in scope; low-since/last-replaced history is supplied by `app` via `state`, not stored here.
- Tests: every validation error class with its config path; golden default config + mini fixture → exposition text; extras added by config only; config fallback order.
