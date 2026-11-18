# app/ module

Owns: FastAPI app, poll loop, meta-metrics, env config. Integrates last; uses `source`, `state`, `metrics` only through `contracts.py` interfaces.

- `create_app()` factory with a lifespan that starts and cancels the poll task. Routes: `/metrics`, `/health`, optional `/status` (no secrets). Debug routes off unless `DEBUG_ROUTES=true`.
- Poll task every `POLL_INTERVAL_SECONDS` (default 30). Catch and log all exceptions inside the loop, including the upstream error body, and count them; let `asyncio.CancelledError` propagate.
- Scrapes read cached values only.
- Meta-metrics: last successful poll timestamp, poll duration, `homematic_poll_errors_total`.
- Single replica only; do not add locking to pretend otherwise.
- Tests use a fake `Source`: loop survives failures, `/metrics` never calls the source, shutdown cancels the task cleanly.
