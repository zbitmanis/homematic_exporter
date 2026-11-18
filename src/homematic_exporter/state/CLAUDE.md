# state/ module

Owns: persistence on the mounted volume (battery history). The auth token is NOT stored here: it comes from env/Podman secret (intent Q4). Imports nothing from other modules.

- API: `FileStateStore(dir)` implements `StateStore` (`load`, `save`); `BatteryHistory(store, tuning).update(devices, now) -> list[BatteryRecord]` (spec 3, 8). Directory from env `STATE_DIR`. Plan: `specs/plans/state.md`.
- Create the directory 0700 and files 0600; verify on startup and fail loudly if looser.
- Write atomically (temp file in same dir + `os.replace`).
- Persists per-device battery history (low-since, last-replaced), keyed by device name, so it survives restarts.
- Never echo values in logs or exceptions.
- Tests use `tmp_path`, including permission assertions.
