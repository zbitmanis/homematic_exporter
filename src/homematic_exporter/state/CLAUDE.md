# state/ module

Owns: persistence on the mounted volume (battery history). The auth token is NOT stored here: it comes from env/Podman secret (intent Q4). Imports only the shared contracts (`contracts`, `config_models`, `redact`), never other modules. State reads no environment: the app passes `STATE_DIR` to `FileStateStore`. Plan: `specs/plans/state.md`.

## Public API (`homematic_exporter.state`)
- `FileStateStore(dir)` implements `StateStore` (`load`, `save`). Raises `StateDirError` (no paths in the message) for a directory with any group/other permission bits, a non-directory, a directory not owned by the current user, or a missing parent (only the final directory is created, mode 0700). Only the directory is permission-checked; files are always written 0600. Stale `.*.tmp` files from a crashed write are removed at start (best effort).
- `FileStateStore.load(key)` returns `None` for a missing, corrupt, non-object, non-finite or oversized (> `MAX_STATE_BYTES`) file, with one warning (no values). `save(key, value)` is atomic (temp file in the same dir, fsync, `os.replace`, best-effort directory fsync) and raises `OSError` on write failure.
- Keys must match `^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` and contain no `..`, else `ValueError("invalid state key")`.
- `BatteryHistory(store, tuning).update(devices, now) -> list[BatteryRecord]` (spec 3, 8). Never raises `OSError`: a failed save logs one warning (exception type only) and is retried on the next update; records are still returned. Raises `ValueError("invalid timestamp")` for a non-finite or out-of-range `now`. Malformed stored records (or an unknown `version`) are dropped with a warning and the store is rewritten.
- Stored under key `battery`: `{"version": 1, "records": {name: {room, device_type, low_since, last_replaced, last_seen_day}}}`.

## Rules
- The state directory must be used by ONE process (single replica); there is no locking.
- A failing save is logged at most once per 15 minutes (by injected time), plus one INFO line on recovery.
- Special files (FIFO, directory) and symlinks as state files are rejected (warning, `None`). Only this store's own temp files older than 5 minutes are cleaned at start.
- Stored timestamps outside 1970..2100 and days outside 2000..2100 mark a record malformed.
- One shared `BatteryHistory` instance, called from the single poll task (no locking). `update` is synchronous with blocking fsync: the app runs it off the event loop.
- Never echo values or paths in logs or exceptions.
- Time is injected (`now`), never read inside the module.
- Tests use `tmp_path`, including permission assertions.
- Allowed paths for this module are enforced by `.claude/ownership.yaml` (CI check and path-guard hook); anything else goes under "Requests" in your plan.
