# Spec: Homematic IP heating exporter

- **Status:** draft for owner review (generated from `intent/homematic-exporter.intent.md`, accepted 2026-11-18)
- **Inputs:** intent, `docs/spikes/homematicip-spike.md`, the captured fixture (20 devices, 12 rooms; local only), `docs/sbom/components.md`, `docs/ci/README.md`
- **Next artifact:** one plan per module task in `specs/plans/<module>.md` (template in `specs/README.md`); master plan, review phases and review log in `specs/plan.md`

## 1. Summary

A single-replica Python service. A background task downloads the Homematic IP configuration every `POLL_INTERVAL_SECONDS`, parses it into an immutable `Snapshot`, updates Prometheus metrics from the mounted `config.yaml`, and tracks accumulator (battery) history on a state volume. `/metrics` serves cached values only. Read-only: it never writes to the heating system.

**Mapping is configuration, structure is code.** A mounted `config.yaml` (same idea as the Viessmann exporter's `/etc/viessman/config`) holds everything that may change without a code change: model-to-type names, raw field names, channel types, metric definitions, scaling and thresholds. Code keeps what is logic: the graph joins (device to room, naming, valves per room), battery history, derived metrics and polling.

```
 Homematic IP cloud --(library: auth, rate limit, download)--> raw JSON dict
                                                                     |
        SOURCE_KIND=file (JSON file) --------------------------------+
                                                                     v
   source/parser.parse_snapshot(raw) --> Snapshot ---> app poll loop ---> state.BatteryHistory (volume)
                                                              |                 |
                                                              +--> metrics.Registry.update(snapshot, batteries)
 Prometheus --> GET /metrics (cache only) <-------------------+
```

## 2. Requirements (numbered, testable)

**Polling and resilience**
- R1. The poll task runs every `POLL_INTERVAL_SECONDS` (default 60) and updates metrics from one `Snapshot`. `/metrics` never calls the source (test: fake source call count stays flat across scrapes).
- R2. A failed poll (any exception except `CancelledError`) is caught, logged with the upstream error body (scrubbed of credentials), counted in `homematic_poll_errors_total`, and the loop continues. Last good values stay exported.
- R3. `homematic_last_successful_poll_timestamp_seconds` advances only on success. `homematic_data_age_seconds` is computed at scrape time (`Gauge.set_function`) as now minus that timestamp; before the first success it is not exported.
- R4. Each upstream call has an explicit timeout (`HTTP_TIMEOUT_SECONDS`, default 10). A poll that exceeds the interval does not overlap the next one (single task, sequential).
- R5. On shutdown the poll task is cancelled and awaited; no leaked tasks.

**Data and metrics**
- R6. All entity metrics (rooms, devices, valves, contacts, batteries) are defined in the mounted `config.yaml`; adding one, including a new numeric raw field via `extract.extras`, needs no Python change (test: add an entry, see the series).
- R7. Metric names follow `homematic_<thing>_<unit>`; counters end `_total`; base units (celsius, ratio, seconds). Allowed labels: `room`, `device_type`, `device`.
- R8. A value that is `None` in the snapshot produces **no series** (the series is removed if it existed). A device or room absent from a new snapshot has all its series removed. (Real case: room `girts` has no temperature/humidity while its sensor is unreachable.)
- R9. Series count stays bounded: about 230 for the captured installation (see 6.7). Labels never contain SGTIN, serial, id or timestamp.
- R10. Humidity is exported as a ratio 0-1 (source percent / 100). Valve position is a ratio 0-1 as reported.

**Battery / accumulator readiness**
- R11. Per device: `low_battery`, `unreachable`, `undervoltage`, `rssi_dbm` are exported from the device base channel.
- R12. Battery history survives restarts: `low_since` (set when `lowBat` becomes true, cleared when false) and `last_replaced` (set when `lowBat` goes true to false). Written atomically to `STATE_DIR` (dir 0700, files 0600); startup fails if permissions are looser.
- R13. An unreachable device keeps its previous `lowBat` state (no transition is inferred while unreachable).
- R14. History records for devices not seen for `tuning.state_retention_days` (default 90) are pruned.

**Configuration**
- R19. `config.yaml` is validated at startup against a strict schema (unknown keys rejected, names/labels/scopes/fields/transforms checked); any error fails startup with the config path of the problem (for example `metrics[3].labels[1]: unknown label 'sgtin'`).
- R20. `python -m homematic_exporter.check_config [--config PATH] [--fixture PATH]` validates a config and, with a fixture, prints the series it would produce. It is a **tool module** (task 4, see section 12): it may import every module, because the fixture-to-series path needs `source.parse_snapshot` and `metrics` may not import `source`. CI runs it against the shipped default config and the mini fixture and compares golden exposition text.
- R21. Config location: `CONFIG_FILE` if set (must exist, else fail); otherwise `/etc/homematic-exporter/config/config.yaml` if present (the pod/volume mount); otherwise the default bundled in the image (`/app/default-config.yaml`). The chosen source is logged at INFO. The mount is read-only; the exporter never writes to it. Changes take effect on restart.

**Config generator**
- R22. `python -m homematic_exporter.generate_config --state STATE.json [--existing CONFIG] --out CONFIG` writes a draft `config.yaml` from a Homematic IP state JSON (intent "Config generator"): `device_models` for every observed model, valve/contact rules for observed channel types, metric entries for observed fields per scope, and comments for unmapped fields. Deterministic; output contains no SGTIN, id, token, PIN, room or device name; the output passes `check_config` against the same input.

**Security and ops**
- R15. `HMIP_AUTH_TOKEN` and `HMIP_ACCESS_POINT` come from the environment only; they never appear in logs, metrics, `/status`, exceptions or the image.
- R16. Debug routes are off unless `DEBUG_ROUTES=true`.
- R17. `/health` returns 200 while the poll task is alive, 503 if it died. It does not fail because the upstream is down (alerts cover that).
- R18. The image runs as a non-root user, ships `/licenses/`, and starts with one `CMD`.

## 3. Module interfaces (mirror `docs/sbom/components.md`)

`src/homematic_exporter/contracts.py` (land first, human-reviewed; changes need a spec change):

```python
Extras = Mapping[str, float | str | bool | None]   # config-defined raw fields (extract.extras)

@dataclass(frozen=True, slots=True)
class Room:
    name: str
    temperature_celsius: float | None
    setpoint_celsius: float | None
    humidity: float | None                 # raw source value (percent); scaled by the metric definition
    control_mode: str | None               # raw, e.g. "AUTOMATIC"
    window_state: str | None               # raw, e.g. "OPEN" | "TILTED" | "CLOSED"
    extras: Extras

@dataclass(frozen=True, slots=True)
class Device:
    name: str                              # "<room> <device_type>", unique (see 4)
    room: str                              # "system" if not in exactly one room
    device_type: str                       # from extract.device_models
    low_battery: bool | None
    unreachable: bool | None
    undervoltage: bool | None
    rssi_dbm: int | None
    extras: Extras

@dataclass(frozen=True, slots=True)
class Valve:
    room: str
    device_type: str                       # from the extract.valves rule, e.g. "floor-valve"
    device: str                            # "<room> floor-valve" or the radiator device name
    position_ratio: float | None
    actual_temperature_celsius: float | None   # where the rule maps it (radiators)
    extras: Extras

@dataclass(frozen=True, slots=True)
class Contact:
    room: str; device_type: str; device: str
    window_state: str | None               # raw
    extras: Extras

@dataclass(frozen=True, slots=True)
class Snapshot:
    taken_at: float                        # unix seconds, UTC
    rooms: tuple[Room, ...]
    devices: tuple[Device, ...]
    valves: tuple[Valve, ...]
    contacts: tuple[Contact, ...]

@dataclass(frozen=True, slots=True)
class BatteryRecord:
    device: str; room: str; device_type: str
    low_since: float | None                # unix seconds
    last_replaced: float | None

class UpstreamError(Exception):            # status, body (scrubbed by the raiser)
    status: int | None
    body: str

class Source(Protocol):
    async def fetch(self) -> Snapshot: ...  # raises UpstreamError

class StateStore(Protocol):
    def load(self, key: str) -> dict | None: ...
    def save(self, key: str, value: dict) -> None: ...   # atomic
```

`src/homematic_exporter/config_models.py` is the second shared contract (added in the contracts task, see `specs/plan.md`): pydantic models `ExtractConfig` (with `ValveRule`, `ContactRule`, `ExtraField`) and `Tuning`, the validated `extract` and `tuning` sections of `config.yaml`. They must be shared because `source` needs `ExtractConfig` and `state` needs `Tuning`, while modules may not import each other; `metrics` composes them into `AppConfig` together with the metric definitions. Same rule as `contracts.py`: changes need a spec change in the same commit.

`src/homematic_exporter/redact.py` is the third shared contract (phase-2 readiness task): pure `scrub(text, secrets) -> str` that replaces the given secrets, credential-looking `key[:=]value` pairs (`authToken`, `CLIENTAUTH`, `Authorization`, `pin`, `token`, also quoted JSON and `Bearer`) and 24-hex SGTINs with `[REDACTED]`. Anything that raises or logs upstream text uses it: `source` when it builds `UpstreamError` bodies, `app` in a logging filter for every other exception (R15, section 9).

`contracts.py` also defines `NameCollisionError` and `CollisionPolicy = Literal["error", "suffix"]` (see `parse_snapshot` below and C1). Dataclasses holding `extras` are frozen but not hashable; key collections by name.

| Module | Public interface | Notes |
|---|---|---|
| `source` | `CloudSource(access_point, token, timeout, extract)`, `FileSource(path, extract)`, `parse_snapshot(raw: dict, now: float, extract: ExtractConfig, on_collision: CollisionPolicy = "error") -> Snapshot` | Cloud uses `homematicip` `AsyncHome.init_async` + `download_configuration_async()` and parses the **raw JSON** itself, so tests need only the fixture and the library's object model is not a dependency of the parser. `FileSource` reads the same JSON (e2e, demos). `on_collision="error"` raises `NameCollisionError`; `"suffix"` appends `-2`, `-3` ordered by SGTIN. Upstream failures raise `UpstreamError` with a body scrubbed by `redact.scrub`. |
| `state` | `FileStateStore(dir)`, `BatteryHistory(store: StateStore, tuning: Tuning)`, `BatteryHistory.update(devices: Sequence[Device], now: float) -> list[BatteryRecord]` | History logic (R12-R14, section 8) lives here; depends only on `contracts` and `config_models`. Returns records **only for devices in the given list** (R8); records of absent devices stay stored until pruned. |
| `metrics` | `load_config(path) -> AppConfig` (schema, validation, R19-R21), `Registry.build(metric_defs, tuning)`, `Registry.update(snapshot, batteries)`, `Registry.record_success(timestamp, duration)`, `Registry.record_error()`, `Registry.exposition() -> bytes`, `render(config, snapshot, batteries=()) -> bytes` | Pure; one private `CollectorRegistry`. Owns the config schema (pydantic v2, `extra=forbid`) and **all** metrics including derived (6.5) and meta (6.6): `app` only calls `record_success`/`record_error`. `homematic_data_age_seconds` has no series until the first `record_success`. `render` builds a registry, updates it and returns the exposition: golden tests use a hand-built `Snapshot`. `source` and `state` receive their config sections as typed objects. |
| `app` | `create_app(*, settings=None, config=None, source=None, store=None) -> FastAPI` | All parameters default to values derived from the environment, so `uvicorn --factory homematic_exporter.app:create_app` works with no arguments; tests inject fakes. `app/wiring.py` is the only place that imports concrete `source`, `state` and `metrics` implementations; the rest of `app` uses the contract protocols. Lifespan owns the poll task, calls `record_success`/`record_error`, installs a logging filter built on `redact.scrub` (secrets from settings), and passes `on_collision="error"` until the first successful poll, then `"suffix"` with a WARNING (C1). |
| tools (`check_config.py`, `generate_config.py`, top-level) | `python -m homematic_exporter.check_config`, `python -m homematic_exporter.generate_config` | Task 4 and 5. May import every module; not part of the runtime path. Own the fixture-to-exposition integration golden test. |

## 4. Parsing rules (source module, verified on the fixture)

The **structure** below is code; every raw name, channel type and label shown is the **default value** from `config.yaml` (section 5.1), not a constant in Python.

- **Rooms:** groups with `type == "HEATING"`; room name = group `label`. Fields: `actualTemperature`, `setPointTemperature`, `humidity`, `controlMode`, `windowState`.
- **Device to room:** a device belongs to the room whose `HEATING` group lists it in `channels[].deviceId`. A device in exactly one room gets that room; in none or several rooms (the floor controller touches 8; the access point and circulation pump touch none) gets room `system`.
- **Model to device_type** (`extract.device_models`): `HmIP-eTRV-B-2 R4M` radiator-thermostat, `HmIP-STH` temp-humidity-sensor, `HmIP-STHD` temp-humidity-display, `HmIP-WTH-1` wall-thermostat, `HmIP-SWDM-2` door-window-contact, `HmIP-FALMOT-C12` floor-controller, `HmIP-FSM` circulation-pump-switch, `HmIP-HAP JS1` access-point. An unmapped model becomes the lowercased model string and logs a warning once.
- **Device name:** `"<room> <short-model>"`. Fixture check: 20 devices, 0 collisions. A collision at **startup** is fatal (intent Q7). On **later polls** a colliding name gets a `-2`, `-3` suffix (ordered by SGTIN, which is never exported), a WARNING is logged once per new collision, and the exporter keeps serving (C1, decided).
- **Battery/radio fields** come from the channel whose type is `DEVICE_BASE*`, `DEVICE_OPERATIONLOCK` or `ACCESS_CONTROLLER_CHANNEL`: `lowBat`, `unreach`, `deviceUndervoltage`, `rssiDeviceValue`.
- **Valves:** every `FLOOR_TERMINAL_BLOCK_MECHANIC_CHANNEL` with a non-empty `groups` list becomes a `floor-valve` for the room that group names (channel 12 is unused and skipped); every `HEATING_THERMOSTAT_CHANNEL` becomes a `radiator-thermostat` valve for its device's room. Fixture: 11 floor + 4 radiator valves, each in exactly one room.
- **Contacts:** `SHUTTER_CONTACT_CHANNEL.windowState`; `OPEN` or `TILTED` means open, `CLOSED` closed.
- Fields listed in `extract.extras` are read from the group (scope `room`), the device base channel (`device`) or the matched channel (`valve`, `contact`) and stored in `extras` under the configured key.
- Unknown or missing fields map to `None`, never raise.

## 5. Config (environment, with defaults)

| Variable | Default | Notes |
|---|---|---|
| `HMIP_ACCESS_POINT` | required for `cloud` | SGTIN; secret-adjacent, never logged |
| `HMIP_AUTH_TOKEN` | required for `cloud` | Podman secret / env; never logged |
| `SOURCE_KIND` | `cloud` | `cloud` or `file` |
| `SOURCE_FILE` | none | JSON path when `SOURCE_KIND=file` |
| `POLL_INTERVAL_SECONDS` | `60` | decided in C8 |
| `HTTP_TIMEOUT_SECONDS` | `10` | per upstream call |
| `STATE_DIR` | `/state` | battery history |
| `CONFIG_FILE` | unset | see R21: explicit path (must exist), else `/etc/homematic-exporter/config/config.yaml`, else the bundled default |
| `LISTEN_HOST` / `LISTEN_PORT` | `0.0.0.0` / `9100` | |
| `LOG_LEVEL` | `INFO` | |
| `DEBUG_ROUTES` | `false` | enables `/status` (counts, last poll info, no secrets) |

### 5.1 `config.yaml` (mounted read-only; default bundled in the image)

Environment keeps secrets and operations (token, access point, ports, intervals, paths). `config.yaml` keeps mapping and non-secret tuning. Default content (abridged; the full file ships as `config/default-config.yaml`):

```yaml
version: 1
tuning:
  heat_demand_min_position: 0.0     # valve position above this counts as open
  state_retention_days: 90
extract:
  system_room: system
  room_group_type: HEATING          # groups of this type are rooms; room name = group label
  device_models:                    # raw modelType -> device_type label
    "HmIP-eTRV-B-2 R4M": radiator-thermostat
    "HmIP-STH": temp-humidity-sensor
    "HmIP-STHD": temp-humidity-display
    "HmIP-WTH-1": wall-thermostat
    "HmIP-SWDM-2": door-window-contact
    "HmIP-FALMOT-C12": floor-controller
    "HmIP-FSM": circulation-pump-switch
    "HmIP-HAP JS1": access-point
  rooms:                            # Room attribute: raw group field
    temperature_celsius: actualTemperature
    setpoint_celsius: setPointTemperature
    humidity: humidity
    control_mode: controlMode
    window_state: windowState
  device_flags:                     # Device attribute: raw field on the device base channels
    low_battery: lowBat
    unreachable: unreach
    undervoltage: deviceUndervoltage
    rssi_dbm: rssiDeviceValue
  valves:
    - channel_type: FLOOR_TERMINAL_BLOCK_MECHANIC_CHANNEL
      device_type: floor-valve
      room_from: channel_groups     # room named by the channel's HEATING group; skip if none
      fields: { position_ratio: valvePosition }
    - channel_type: HEATING_THERMOSTAT_CHANNEL
      device_type: radiator-thermostat
      room_from: device_room
      fields: { position_ratio: valvePosition, actual_temperature_celsius: valveActualTemperature }
  contacts:
    - channel_type: SHUTTER_CONTACT_CHANNEL
      fields: { window_state: windowState }
  extras: []                        # e.g. - { scope: room, key: boost_duration, field: boostDuration }
metrics:
  - { name: homematic_room_temperature_celsius, help: Room temperature, type: gauge,
      scope: rooms, value: temperature_celsius, labels: [room] }
  - { name: homematic_room_humidity_ratio, help: Room relative humidity, type: gauge,
      scope: rooms, value: humidity, scale: 0.01, labels: [room] }
  - { name: homematic_room_automatic_mode, help: 1 if the room is in automatic mode, type: gauge,
      scope: rooms, value: control_mode, transform: { equals: AUTOMATIC }, labels: [room] }
  - { name: homematic_room_window_open, help: 1 if the window is open or tilted, type: gauge,
      scope: rooms, value: window_state, transform: { in: [OPEN, TILTED] }, labels: [room] }
  # ... one entry per row of 6.2 - 6.4
```

Why not paths like the Viessmann config: the Homematic JSON is a graph (rooms are groups that list device channels). Joins stay in code; only names and rules are configurable.

## 6. Metric catalogue

### 6.1 Metric definition schema (the `metrics:` list of `config.yaml`)

```yaml
- name: homematic_room_temperature_celsius   # ^homematic_[a-z0-9_]+$
  help: Room temperature
  type: gauge                  # gauge only for entity metrics in v1
  scope: rooms                 # rooms | devices | valves | contacts | batteries
  value: temperature_celsius   # attribute of the contracts dataclass, or extras.<key>
  labels: [room]               # subset of the scope's label fields; allowed: room, device_type, device
  scale: 1.0                   # optional multiplier (humidity: 0.01)
  transform: none              # none | bool | { equals: X } | { in: [A, B] }  -> 1/0
```
**Scope and label mapping** (one table, used by validation and the registry):

| Metric `scope` | `extract.extras` `scope` | Label `room` | Label `device_type` | Label `device` | `value` attributes |
|---|---|---|---|---|---|
| `rooms` | `room` | `Room.name` | - | - | `Room.*`, `extras.<key>` |
| `devices` | `device` | `Device.room` | `Device.device_type` | `Device.name` | `Device.*`, `extras.<key>` |
| `valves` | `valve` | `Valve.room` | `Valve.device_type` | `Valve.device` | `Valve.*`, `extras.<key>` |
| `contacts` | `contact` | `Contact.room` | `Contact.device_type` | `Contact.device` | `Contact.*`, `extras.<key>` |
| `batteries` | - | `BatteryRecord.room` | `BatteryRecord.device_type` | `BatteryRecord.device` | `low_since`, `last_replaced` |

(`extras` scopes are singular, metric scopes plural; the mapping is fixed.)

Validation (R19), at startup: name pattern and uniqueness, labels within the whitelist and available for the scope, scope and value exist, transform valid, `scale` numeric. `yaml.safe_load` only; unknown keys rejected.

### 6.2 Room metrics (entity `rooms`, label `room`)

| Metric | Source field | Notes |
|---|---|---|
| `homematic_room_temperature_celsius` | HEATING `actualTemperature` | group value; individual sensors are not exported in v1 |
| `homematic_room_setpoint_celsius` | `setPointTemperature` | |
| `homematic_room_humidity_ratio` | `humidity`, `scale: 0.01` | percent to ratio |
| `homematic_room_automatic_mode` | `control_mode`, `transform: {equals: AUTOMATIC}` | 1 automatic, 0 manual |
| `homematic_room_window_open` | `window_state`, `transform: {in: [OPEN, TILTED]}` | omitted when `None` |

### 6.3 Valve and contact metrics (labels `room`, `device_type`, `device`)

| Metric | Entity.field | Notes |
|---|---|---|
| `homematic_valve_position_ratio` | valves.position_ratio | floor channels and radiators |
| `homematic_valve_actual_temperature_celsius` | valves.actual_temperature_celsius | radiators only |
| `homematic_contact_open` | contacts.window_state, `transform: {in: [OPEN, TILTED]}` | door/window contact |

### 6.4 Device and battery metrics (labels `room`, `device_type`, `device`)

| Metric | Source | Notes |
|---|---|---|
| `homematic_device_low_battery` | `lowBat` | 1 low. Alert: any = 1, "prepare charged accumulators" |
| `homematic_device_unreachable` | `unreach` | alert when 1 for 15 m |
| `homematic_device_undervoltage` | `deviceUndervoltage` | |
| `homematic_device_rssi_dbm` | `rssiDeviceValue` | dBm; omitted when `None` |
| `homematic_device_battery_low_since_timestamp_seconds` | `BatteryRecord.low_since` | omitted when not low |
| `homematic_device_battery_last_replaced_timestamp_seconds` | `BatteryRecord.last_replaced` | persists across restarts |

### 6.5 Derived (built in, no labels)

| Metric | Definition |
|---|---|
| `homematic_valves_open` | count of valves with position > `tuning.heat_demand_min_position` |
| `homematic_heat_demand` | 1 if `homematic_valves_open` > 0 else 0 (proxy for boiler demand; boiler/pump `on` is not reported by this installation) |

### 6.6 Meta (built in)

| Metric | Type | Definition |
|---|---|---|
| `homematic_last_successful_poll_timestamp_seconds` | gauge | unix time of the last success |
| `homematic_data_age_seconds` | gauge (set_function) | now minus the above |
| `homematic_poll_duration_seconds` | gauge | duration of the last poll |
| `homematic_poll_errors_total` | counter | failed polls |
| `homematic_exporter_build_info` | gauge, label `version` | constant 1 |

### 6.7 Cardinality (captured installation)
12 rooms x 5 + 20 devices x 6 + 15 valves x 2 + 1 contact + ~10 derived/meta, about 230 series. A change that multiplies this needs justification in its PR.

### 6.8 Suggested alerts (`deploy/prometheus-alerts.yml`, not code)
- Stale data: `homematic_data_age_seconds > 300`
- Errors: `increase(homematic_poll_errors_total[10m]) > 0` for 10 m
- Accumulators: `homematic_device_low_battery == 1` (labels name the device and room)
- Unreachable: `homematic_device_unreachable == 1` for 15 m
- Radio: `homematic_device_rssi_dbm < -85` for 1 h

## 7. HTTP surface

| Route | Behaviour |
|---|---|
| `GET /metrics` | Prometheus text exposition from the private registry; cache only |
| `GET /health` | `{"status":"ok"}` 200 while the poll task is alive; 503 if dead |
| `GET /status` | only when `DEBUG_ROUTES=true`: counts, last poll time/duration, no secrets |

## 8. Battery history algorithm (state module)

Per device name, persisted as JSON under key `battery`:
- first sight, `lowBat = true`: `low_since = now` (approximate: true start unknown, see C3)
- `false` to `true`: `low_since = now`
- `true` to `false`: `last_replaced = now`, `low_since = None`
- unreachable device (`unreachable` is true): record unchanged (R13); if it has no record yet, create one with `low_since = None` and no `last_replaced` (no state is inferred)
- `low_battery` is `None` (unknown): record unchanged, no transition
- save only when a record changed; atomic write (temp file + `os.replace`)
- prune records unseen for `tuning.state_retention_days` (R14)
- `update` returns records for the devices passed in only (R8)
- a renamed device is a new record (old one is pruned later)

## 9. Logging

`logging` with a stable single-line format. On poll failure: level `ERROR`, message includes status and upstream body after `redact.scrub(text, secrets=[HMIP_AUTH_TOKEN, HMIP_ACCESS_POINT])` (also removes SGTIN-like 24-hex strings and `AUTHTOKEN`/`CLIENTAUTH`/`Authorization`/`pin`/`token` values). `app` installs a logging filter that applies the same function to every record, so unexpected exceptions are scrubbed too. Never `repr()` of settings or request objects.

## 10. Test strategy

- **Fixtures:** `tests/source/fixtures/mini_state.json`, hand-written and scrubbed, derived from the capture: three rooms, ten devices incl. an access point (`ACCESS_CONTROLLER_CHANNEL`), one `lowBat`, one unreachable device (room with `None` temperature), floor channels with and without groups, a device in several rooms, a closed and an open contact, an unmapped model and an `extras` example (`boostDuration`). The `collision_state` fixture in `tests/conftest.py` derives a variant with two same-named devices. `default_extract` and `default_tuning` fixtures load `config/default-config.yaml`, the single shared copy. The full capture stays local and git-ignored.
- **Unit:** parser (every rule in section 4, golden `Snapshot`), `BatteryHistory` (transitions, unreachable, prune, restart), `Registry` (golden exposition text from a hand-built `Snapshot`, series removal, label whitelist, YAML validation errors), settings parsing, `redact.scrub`, and the import-boundary test (`tests/test_import_boundaries.py`).
- **App:** fake `Source`: failures counted and survived, `/metrics` never calls the source, `/health` 503 when the task dies, clean shutdown, no secrets in logs (caplog assertions).
- **E2E (`tests/e2e/`, `pytest -m e2e`):** start the app with `SOURCE_KIND=file`; break/replace the file to simulate failures; restart with the same `STATE_DIR`; state permissions; then the same against the built image with `podman run`.
- **Config:** schema tests (every R19 error class, with its config path), the integration golden test (mini fixture through `parse_snapshot` into `render`, compared with a golden exposition file) and `check_config` against the shipped default, both in task 4 where `source` and `metrics` meet, an `extras` test (add a field by config only), and a fallback-order test for R21.
- **Gate:** `ruff check`, `ruff format --check`, `mypy src tests` (strict), `pytest -q`, `pip-audit`, `check_licenses.py`.

## 11. Container and deployment

- Image per `Dockerfile` (multi-stage, non-root uid 10001, `/state` volume, port 9100, `/licenses/`); built for `linux/amd64` and `linux/arm64` by CI.
- The image ships the default config (`COPY config/default-config.yaml /app/default-config.yaml`): **Dockerfile change needed** in task 4 (deploy), not in the metrics task. Operators override it by mounting a directory at `/etc/homematic-exporter/config/` (read-only).
- Podman Quadlet (`deploy/homematic-exporter.container`): single replica, `Secret=` for the token and access point, state volume, read-only root fs, `HealthCmd` against `/health`, port published on the internal network only, `Volume=<config dir>:/etc/homematic-exporter/config:ro` (in a Kubernetes pod: a ConfigMap mounted at the same path).

## 12. Work split (parallel agents, one module per worktree)

1. `contracts.py`, `config_models.py`, `redact.py`, fixture, default `extract`/`tuning` config: done (tasks 1 and 1b), human-reviewed.
2. In parallel, one plan each (`specs/plans/<module>.md`): `source` (parser, `FileSource`, `CloudSource`), `state` (store, battery history), `metrics` (config schema and loading, registry, derived and meta metrics, the `metrics:` list of the default config).
3. `app` (poll loop, routes, wiring, logging filter) against fakes; then e2e.
4. Tools and deployment: `check_config`, integration golden test, Dockerfile update, Quadlet unit, alert rules.
5. `generate_config` (tool module; after the config schema exists).

### 12.1 Rules for phase-2 agents
- Edit only your module's directory under `src/homematic_exporter/<module>/`, its tests under `tests/<module>/`, and your plan `specs/plans/<module>.md`. `metrics` may also edit the `metrics:` list of `config/default-config.yaml` (not `extract`/`tuning`).
- Do **not** edit: `contracts.py`, `config_models.py`, `redact.py`, `specs/spec.md`, `pyproject.toml`, root `CLAUDE.md`, `Dockerfile`, `.github/`, `docs/`, `requirements*.txt`, `tests/conftest.py`. Need a change? Write it into your plan under "Requests" and stop; the coordinator makes it in its own small PR, merged first, and you rebase.
- Add module-local fixtures in your own `tests/<module>/conftest.py`.
- Cross-module imports are forbidden except `contracts`, `config_models`, `redact` (enforced by `tests/test_import_boundaries.py`).

## 13. Flagged concerns and assumptions (owner input welcome)

- **C1. Name collision at runtime (decided by owner: suffix and warn).** Fatal at startup; on later polls suffix `-2`, `-3` ordered by SGTIN, log a warning, keep serving data. Trade-off accepted: a device label can change when devices are added or removed in a room.
- **C2. Group vs device temperatures (decided by owner: room aggregate only).** Room temperature and humidity come from the HEATING group value, one series per room. Per-sensor temperatures are not exported in v1; revisit if a sensor drifts.
- **C3. `low_since` on first sight is approximate (decided by owner: use first-seen time).** The API gives no timestamp for when `lowBat` began; the exporter records when it first saw the device low. Exact for every later transition. The metric help text states this.
- **C4. Stale `lowBat` on unreachable devices (decided by owner: freeze history).** The cloud reports last-known values, and a dead accumulator can show `unreach` before or without `lowBat`. R13 freezes history while a device is unreachable, so a stale flag cannot fake a swap; the `unreachable` metric still alerts. Three devices are unreachable right now in the capture (a radiator thermostat, the `girts` display sensor, the circulation-pump switch): alerts will fire on day one.
- **C5. Floor valve naming.** Floor channels are named `<room> floor-valve` (not individually addressable devices); two channels in one room would collide: handled by C1.
- **C6. `FileSource` ships in the production image (decided by owner: include).** Read-only, off unless `SOURCE_KIND=file`; the container smoke test, demos and credential-free trials run the real image against a fixture file.
- **C7. Library behaviour.** `download_configuration_async` and the `init_async` signature were read from `homematicip` 2.23.1 source; the websocket and library object model are unused. The pinned version plus the fixture protect against API drift.
- **C8. Rate limiting.** The library's own rate limiter stays on; 60 s polling (decided by owner) downloads about 130 KB each time (about 8 MB/hour). Acceptable; raise the interval if the cloud throttles.
- **C9. RSSI unit (decided by owner: dBm, alert at -85).** `homematic_device_rssi_dbm` is exported as the API reports it (captured range -81 to -43); dBm is not an SI base unit but is the conventional Prometheus choice. The suggested alert `homematic_device_rssi_dbm < -85` for 1 h stays in the alert rules and can be tuned.
- **C11. Config typo risk (accepted by owner).** A wrong raw field name in `config.yaml` yields `None` and therefore a missing series, not an error. Mitigations: golden test on the default config, `check_config --fixture` listing series per metric, and a startup log line with the series count; a metric that produces zero series for two consecutive polls logs a warning.
- **C12. Reload (accepted by owner).** Restart to apply config changes (v1). A SIGHUP reload is possible later; not needed for a 60 s-poll hobby exporter.
- **C13. Config file vs env (accepted by owner).** Access point and token stay in env/secrets, never in `config.yaml` (unlike the installation id in the Viessmann config). Consequence the owner wants: the config file contains no secrets or identifying data, so it may be stored in git (this repo or a private config repo). The generator (R22) and `check_config` must keep it that way.
- **C10. Not yet verified live:** nothing here has run against the real API except the one-off state download that produced the fixture.

## 14. Traceability

| Intent item | Where |
|---|---|
| Heating metrics, battery readiness | 6.2 to 6.4, R11-R14, section 8 |
| Q2 field mapping | section 4 |
| Q3 poll | R1, section 5 |
| Q4 token via secret | R15, section 5 |
| Q5 boiler state | 6.5 |
| Q7 device naming | section 4, C1 |
| Config generator script | R22 |
| Config-driven mapping (mounted file, no hardcoded values) | section 5.1, 6.1, R6, R19-R21, C11-C13 |
| CI/CD, image, licensing | section 11, `docs/ci/README.md`, `THIRD_PARTY_NOTICES.md` |
