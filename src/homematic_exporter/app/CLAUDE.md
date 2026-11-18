# app/ module

Plan: `specs/plans/app.md`. Owns: FastAPI app, poll loop, env config, logging filter built on `redact.scrub`. Meta-metrics are owned by `metrics`; `app` only calls `Registry.record_success`/`record_error`. Integrates last. `create_app(*, settings=None, config=None, source=None, store=None)` takes optional parameters with env-derived defaults so `uvicorn --factory` works; concrete implementations are imported only in `app/wiring.py`, everything else uses the contract protocols. Pass `on_collision="error"` to the parser until the first successful poll, then `"suffix"` with a WARNING.

- `create_app()` factory with a lifespan that starts and cancels the poll task. Routes: `/metrics`, `/health`, optional `/status` (no secrets). Debug routes off unless `DEBUG_ROUTES=true`.
- Poll task every `POLL_INTERVAL_SECONDS` (default 60). Catch and log all exceptions inside the loop, including the upstream error body, and count them; let `asyncio.CancelledError` propagate.
- Scrapes read cached values only.
- Meta-metrics: last successful poll timestamp, poll duration, `homematic_poll_errors_total`.
- Single replica only; do not add locking to pretend otherwise.
- Tests use a fake `Source`: loop survives failures, `/metrics` never calls the source, shutdown cancels the task cleanly.
