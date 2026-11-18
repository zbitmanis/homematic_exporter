# metrics/ module

Owns: `metrics.yaml` schema, parsing, and prometheus objects. Pure; imports nothing from other modules.

- `Registry.build(config)` creates metrics from YAML (`yaml.safe_load` only, validated schema); `Registry.update(snapshot)` sets values. Use a private `CollectorRegistry`, not the global one.
- Each YAML entry: source field, metric name, type, labels, unit. Reject names that break `homematic_<thing>_<unit>` or labels outside `room`, `device_type`, `device`.
- Use `Gauge.set_function` for values computed at scrape time (e.g. data age).
- Missing source values remove the series rather than exporting stale numbers.
- Battery metrics (`homematic_device_low_battery`, `homematic_device_unreachable`, low-since and last-replaced timestamps) are in scope; low-since/last-replaced history is supplied by `app` via `state`, not stored here.
- Tests: golden `metrics.yaml` + snapshot → exposition text.
