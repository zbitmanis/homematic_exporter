# app/ module

Plan: `specs/plans/app.md`. Owns: FastAPI app, poll loop, env config, logging filter built on `redact.scrub`. Meta-metrics are owned by `metrics`; `app` only calls `record_success`/`record_error`. Integrates last. `create_app(*, settings=None, config=None, source=None, store=None)` takes optional parameters with env-derived defaults so `uvicorn --factory` works; concrete implementations are imported only in `app/wiring.py`, everything else uses the contract protocols. Call `source.fetch(on_collision="error")` until the first successful poll, then `"suffix"`; a `NameCollisionError` before the first success is logged at ERROR with the names and exits the process (spec R2, C1). Read `CONFIG_FILE` yourself and pass it to `load_config`. Define `app/ports.py` Protocols for what you use from `metrics`/`state`; only `app/wiring.py` may import concrete modules (`tests/test_import_boundaries.py`).

- `create_app()` factory with a lifespan that starts and cancels the poll task. Routes: `/metrics`, `/health`, optional `/status` (no secrets). Debug routes off unless `DEBUG_ROUTES=true`.
- Poll task every `POLL_INTERVAL_SECONDS` (default 60). Catch and log all exceptions inside the loop, including the upstream error body, and count them; let `asyncio.CancelledError` propagate.
- Scrapes read cached values only.
- After each poll call the registry port: `record_success(timestamp, duration)` or `record_error()`. The meta-metrics themselves are defined and owned by `metrics`.
- Single replica only; do not add locking to pretend otherwise.
- Tests use a fake `Source`: loop survives failures, `/metrics` never calls the source, shutdown cancels the task cleanly.
- Allowed paths for this module are enforced by `.claude/ownership.yaml` (CI check and path-guard hook); anything else goes under "Requests" in your plan.
