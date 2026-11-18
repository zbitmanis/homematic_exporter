# source/ module

Owns: Homematic IP client. Nothing outside `source/` and `tests/source/`. Plan: `specs/plans/source.md`. Provides `parse_snapshot(raw, now, extract, on_collision)` (spec 3, 4) and scrubs upstream bodies with `redact.scrub`; gets its `ExtractConfig` from the caller (shared fixture `default_extract` in tests).

- Implement `Source.fetch() -> Snapshot` (async) from `contracts.py`. Read-only; never write to the heating system.
- Cloud API first (access-point token); keep it behind the `Protocol` so a local CCU client can be added without touching other modules.
- Use the `homematicip` library (2.23.1, decided by the spike; GPL-3.0, do not copy its code) for authentication and the configuration download only; parse the raw JSON yourself. No blocking calls on the event loop (wrap with `asyncio.to_thread` if the library is sync).
- Token and access-point ID come from env (`HMIP_AUTH_TOKEN`, `HMIP_ACCESS_POINT`, usually via a Podman secret), injected by `app`; never log them. No pairing code in v1.
- On upstream failure raise a typed error carrying the response body; `app` logs it.
- Tests use recorded fixtures in `tests/source/fixtures/`; no network, no real credentials.
- Confirm field names against fixtures before mapping them (intent open question 2).
