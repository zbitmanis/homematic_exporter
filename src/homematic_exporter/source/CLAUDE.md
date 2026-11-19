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
- `parse_snapshot(raw, now, extract, on_collision="error") -> Snapshot` (pure, `parser.py`). `parse_with_report` (also exported) returns the snapshot plus a `ParseReport` (colliding base names, unmapped raw models); the parser itself logs nothing.
- `FileSource(path, extract, *, clock=time.time)` and `CloudSource(access_point, token, timeout, extract, *, home_factory=None, clock=time.time)` implement `Source.fetch`. The keyword-only `clock` and `home_factory` are test seams; `app` passes only the positional arguments. Both share `SnapshotBuilder` (`builder.py`), which logs one WARNING per **new** collision (a collision that disappears and returns warns again) and one WARNING per unmapped model, names only, bounded and scrubbed.
- `CloudSource` keeps one `AsyncHome` and reuses it; after any failure it is dropped and `init_async` (URL lookup) runs again. Each cloud call (`init_async`, `download_configuration_async`) has its own `asyncio.timeout`, so one `fetch` may take up to twice `timeout`. Errors become `UpstreamError`: message without upstream text, `status` from the library's exception class or its `Error: <code>` message, `body` = `redact.scrub(type + message, secrets=(token, access point))` capped at `MAX_BODY_CHARS`. The error is built in the `except` block but raised after it, so it has neither `__cause__` nor `__context__` (the unscrubbed library exception is not reachable from it; `from None` alone would only hide it from printing). The body is escaped (control characters such as newline and ESC become `\\n`, `\\x1b`) and ends up at most `MAX_BODY_CHARS` long; a timeout body names the timeout; `access_point` and `token` are stripped in the constructor so a trailing newline from a secret file is still redacted. The first `home_factory()` call (it imports `homematicip`) runs in `asyncio.to_thread`. `CancelledError` propagates.
- `homematicip` is imported lazily (`importlib`) in `CloudSource._new_home`, so the file source and parser load without it (it also has no type stubs).

## Decisions on points the spec leaves open
- A payload without a `devices` object and a `groups` object raises `UpstreamError` whose body names the payload type and up to 20 top-level key names, never values (an error page must count as a failed poll, not wipe every series). Everything inside is lenient: wrong types, non-finite numbers, bools where numbers are expected, nested values map to `None`; `rssi_dbm` accepts integral floats within +-1000.
- Names are unique per kind: devices, valves, contacts and rooms each get `-2`, `-3` suffixes (ordered by SGTIN, then device id, then channel number; rooms by group id) and an existing name is never stolen. The reported collision is the base name. Duplicate room labels are a collision like device names. A radiator valve and a contact reuse the device's final name.
- A floor valve whose `groups` name zero or more than one room is skipped (ambiguous). Only groups of `room_group_type` count; duplicated ids in `groups` (the fixture has them) collapse.
- A device model not in `device_models` becomes the stripped, lowercased model; a missing or empty model becomes `unknown`.
- Upstream names are sanitised in the parser: control characters become spaces and room names and unmapped device types are cut to `MAX_NAME_CHARS` (128), so device names stay under 2 x 128 + 1 characters. A `NameCollisionError` lists at most `MAX_REPORTED_COLLISIONS` (20) names (the report and the log list more, the log up to 20 per poll plus a count); the WARNING reads `name collision, suffixing: ...` because it covers rooms, devices, valves and contacts.
- Suffix rule: every name that exists as a base name is reserved, so rooms `a, a, a-2, a-2` become `a, a-3, a-2, a-2-2`: an entity really called `a-2` keeps it.
- A model string with surrounding whitespace is looked up exactly: `" HmIP-STH "` is unmapped (spec 4: unmapped becomes the lowercased model, here stripped and cleaned) and reported. An unlabelled HEATING group is not a room, so a device it lists is in the labelled room only. A device with no room takes `system_room` and collides normally with a real room of that name.
- Channel keys are numbers only when ASCII digits and at most 9 long; any other key sorts last.
- Room labels are stripped; a group without a non-empty string label is not a room. Output order is the input order (devices, then channels by number).
- `extras` values are read-only mappings (`MappingProxyType`) with every configured key of the scope present (`None` when missing or not a scalar).

## Accepted limits
- `FileSource` rejects a symlink as the final path component (`O_NOFOLLOW`), non-regular files and files over `MAX_FILE_BYTES` (8 MiB); symlinked parent directories are followed. Error messages never contain the path. JSON with `NaN`/`Infinity`, over 4300-digit integers or extreme nesting is rejected.
- Not verified live: `CloudSource` runs only against a fake home and the real library's exception classes (first live run is review phase P8). The library logs error response bodies itself (it redacts by key); the `app` logging filter must scrub them (R15), the source cannot.
- The library offers no explicit close, so the reused `AsyncHome` is never closed; one instance lives for the process.
- `CloudSource.fetch` is not safe for concurrent calls (single poll task by design).
- There is no size cap on the cloud response: the library reads and decodes it fully before the parser sees it.
- The library logs error bodies and request URLs itself (it redacts by key only) and trusts the `urlREST` it gets from the lookup response (TLS is on): the `app` logging filter must scrub (R15) and the exporter relies on the pinned version.
- `FileSource` is for tests and demos only: parsing the JSON amplifies memory about 30x (an 8 MiB file of `[],` costs about 260 MB).
- The parser is O(devices x channels x rules + groups); the 130 KB capture takes milliseconds.
