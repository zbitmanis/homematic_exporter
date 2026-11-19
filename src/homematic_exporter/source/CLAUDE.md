# source/ module

Owns: Homematic IP client. Nothing outside `source/` and `tests/source/`. Plan: `specs/plans/source.md`. Provides `parse_snapshot(raw, now, extract, on_collision)` (spec 3, 4) and scrubs upstream bodies with `redact.scrub`; gets its `ExtractConfig` from the caller (shared fixture `default_extract` in tests).

- Implement `Source.fetch(on_collision: CollisionPolicy = "error") -> Snapshot` (async) from `contracts.py`. Read-only; never write to the heating system.
- Cloud API first (access-point token); keep it behind the `Protocol` so a local CCU client can be added without touching other modules.
- Use the `homematicip` library (2.23.1, decided by the spike; GPL-3.0, do not copy its code) for authentication and the configuration download only; parse the raw JSON yourself. No blocking calls on the event loop (wrap with `asyncio.to_thread` if the library is sync).
- Token and access-point ID come from env (`HMIP_AUTH_TOKEN`, `HMIP_ACCESS_POINT`, usually via a Podman secret), injected by `app`; never log them. No pairing code in v1.
- On upstream failure raise a typed error carrying the response body; `app` logs it.
- Tests use the shared fixtures: `tests/fixtures/mini_state.json` and the `collision_state`, `default_extract` fixtures in `tests/conftest.py` (all protected: request changes in your plan). Module-local fixtures go in `tests/source/conftest.py`. No network, no real credentials.
- Confirm field names against fixtures before mapping them (intent open question 2).
- Allowed paths for this module are enforced by `.claude/ownership.yaml` (CI check and path-guard hook); anything else goes under "Requests" in your plan.

## Public API (`homematic_exporter.source`)
- `parse_snapshot(raw, now, extract, on_collision="error") -> Snapshot` (pure, `parser.py`). `parse_with_report` returns the snapshot plus a `ParseReport` (colliding base names, unmapped raw models); the parser itself logs nothing.
- `FileSource(path, extract, *, clock=time.time)` and `CloudSource(access_point, token, timeout, extract, *, home_factory=None, clock=time.time)` implement `Source.fetch`. The keyword-only `clock` and `home_factory` are test seams; `app` passes only the positional arguments. Both share `SnapshotBuilder` (`builder.py`), which logs one WARNING per **new** collision (a collision that disappears and returns warns again) and one WARNING per unmapped model, names only, bounded and scrubbed.
- `CloudSource` keeps one `AsyncHome` and reuses it; after any failure it is dropped and `init_async` (URL lookup) runs again. Each cloud call (`init_async`, `download_configuration_async`) has its own `asyncio.timeout`, so one `fetch` may take up to twice `timeout`. Errors become `UpstreamError`: message without upstream text, `status` from the library's exception class or its `Error: <code>` message, `body` = `redact.scrub(type + message, secrets=(token, access point))` capped at `MAX_BODY_CHARS`. Raised `from None` so the unscrubbed library exception is not in the chain. `CancelledError` propagates.
- `homematicip` is imported lazily (`importlib`) in `CloudSource._new_home`, so the file source and parser load without it (it also has no type stubs).

## Decisions on points the spec leaves open
- A payload without a `devices` object and a `groups` object raises `UpstreamError` (an error page must count as a failed poll, not wipe every series). Everything inside is lenient: wrong types, non-finite numbers, bools where numbers are expected, nested values map to `None`; `rssi_dbm` accepts integral floats within +-1000.
- Names are unique per kind: devices, valves, contacts and rooms each get `-2`, `-3` suffixes (ordered by SGTIN, then device id, then channel number; rooms by group id) and an existing name is never stolen. The reported collision is the base name. Duplicate room labels are a collision like device names. A radiator valve and a contact reuse the device's final name.
- A floor valve whose `groups` name zero or more than one room is skipped (ambiguous). Only groups of `room_group_type` count; duplicated ids in `groups` (the fixture has them) collapse.
- A device model not in `device_models` becomes the stripped, lowercased model; a missing or empty model becomes `unknown`.
- Room labels are stripped; a group without a non-empty string label is not a room. Output order is the input order (devices, then channels by number).
- `extras` values are read-only mappings (`MappingProxyType`) with every configured key of the scope present (`None` when missing or not a scalar).

## Accepted limits
- `FileSource` rejects a symlink as the final path component (`O_NOFOLLOW`), non-regular files and files over `MAX_FILE_BYTES` (8 MiB); symlinked parent directories are followed. Error messages never contain the path. JSON with `NaN`/`Infinity`, over 4300-digit integers or extreme nesting is rejected.
- Not verified live: `CloudSource` runs only against a fake home and the real library's exception classes (first live run is review phase P8). The library logs error response bodies itself (it redacts by key); the `app` logging filter must scrub them (R15), the source cannot.
- The library offers no explicit close, so the reused `AsyncHome` is never closed; one instance lives for the process.
- `CloudSource.fetch` is not safe for concurrent calls (single poll task by design).
- The cloud response is parsed after the library has fully read it; there is no size cap there (only the file source has one).
- The parser is O(devices x channels x rules + groups); the 130 KB capture takes milliseconds.
