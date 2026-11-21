# Plan: Task 3 - `app` module and e2e

- **Spec:** sections 3, 7, 9, 11, R1-R5, R15-R18
- **Branch:** `feat/app` (from merged `main`)
- **Depends on:** tasks 2a-2c merged (it wires the concrete `source`, `state` and `metrics` in `app/wiring.py` only)

## Files that change
| Path | Change |
|---|---|
| `src/homematic_exporter/app/` | `create_app(...)`, settings from env, `wiring.py` (only place importing concrete implementations), poll task in the lifespan, routes `/metrics` `/health` `/status`, logging filter built on `redact.scrub` |
| `src/homematic_exporter/app/settings.py` (or equivalent) | reads the environment, incl. `CONFIG_FILE` and `APP_VERSION` (passed to `Registry.build` as `version`) |
| `src/homematic_exporter/app/ports.py` | local Protocols for the registry (`update`, `record_success`, `record_error`, `exposition`), battery history and config (`extract`, `tuning`) |
| `src/homematic_exporter/app/wiring.py` (state) | construct `FileStateStore(STATE_DIR)` (read `STATE_DIR` in settings; map `StateDirError` to a non-zero exit with a path-free log line), pass `config.tuning` to `BatteryHistory`, call `update(devices, snapshot.taken_at)` from the single poll task via `asyncio.to_thread` (it does a blocking `fsync`), keep ONE shared instance; `update` never raises `OSError` (spec 3) but may raise `ValueError("invalid timestamp")` |
| `tests/app/`, `tests/e2e/` | fake `Source` (honours `on_collision`); `SOURCE_KIND=file` e2e; restart with the same `STATE_DIR`; startup collision exits non-zero |

## Order of work
1. App tests with fakes (loop survives errors, `/metrics` never calls the source, `/health` 503 when the task dies, clean shutdown, no secrets in logs), then the app.
2. E2E with the file source.

## Risks
- Starts only after tasks 2a-2c are merged.
- `uvicorn --factory` must work with no arguments.

## Proof
gate output, e2e output, `verifier` run.

## Rules (spec 12.1)
- Edit only `src/homematic_exporter/app/`, `tests/app/`, `tests/e2e/`, this plan.
- Do not edit contracts (`contracts.py`, `config_models.py`, `redact.py`), the spec, `pyproject.toml`, root `CLAUDE.md`, `Dockerfile`, `.github/`, `docs/`, `requirements*.txt`, `tests/conftest.py`. Put change requests under "Requests" and stop.
- Outside `app/wiring.py`, import only `contracts`, `config_models`, `redact` and your own `app/ports.py` Protocols; `wiring.py` and `tests/e2e/` may import the concrete modules (`tests/test_import_boundaries.py`).
- Tests first; paste gate output (`ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`).

## Closing review task (mandatory, last task of this plan; specs/plan.md section A)
The PR is not opened until every step is done or marked n/a with a reason. Paste each verdict into the PR description. After any HIGH/CRITICAL fix the same reviewer re-checks.
- [ ] R1 Gate: `ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`, `pip-audit`, `check_licenses.py` (output pasted)
- [ ] R2 `python-reviewer` + `fastapi-reviewer`
- [ ] R3 `code-reviewer`
- [ ] R4 `security-reviewer`
- [ ] R5 `architect`: required
- [ ] R6 `code-simplifier` (after R2-R5 are clean; gate re-run)
- [ ] R7 `performance-optimizer`: required: poll duration, memory soak, series count
- [ ] R8 required: `verifier` runs the app; `e2e-runner` runs failure, restart and container scenarios
- [ ] R9 `doc-updater`: `CLAUDE.md`, module `CLAUDE.md`, SBOM manifest, spec catalogue in sync
- [ ] R10 owner PR review and squash merge

## Requirements (from the `source` and `metrics` plans)
- Config: `load_config(CONFIG_FILE)` runs once at startup. It is synchronous pure-Python YAML (up to about 2.6 s at the 256 KiB cap), so it is never called while serving. Catch `ConfigError` (its issues are already scrubbed) and fail startup with them.
- `Registry.build` (raises `ConfigError`) runs at startup with `load_config`: a `ConfigError` is logged with its key paths and the process exits non-zero. In the poll loop `Registry.update` and `Registry.record_success` (raises `ValueError`) stay inside the app's error handling. An exception never ends the poll task; `CancelledError` propagates (R5).
- `Registry.update` and `Registry.exposition` are CPU-bound (about 1 ms at 20 devices, under 100 ms at 2000) and touch memory only: call them directly on the event loop, not through `asyncio.to_thread`.
- `/metrics` is served with `prometheus_client.CONTENT_TYPE_LATEST`.
- Logging: the filter built on `redact.scrub` is installed on the library's logger as well as the app's. `homematicip` logs error response bodies and request URLs itself (it redacts by key only), and `source` cannot scrub them.
- Timing: one `CloudSource.fetch` can take up to 2x `HTTP_TIMEOUT_SECONDS` (separate timeouts for `init_async` and the download). Size `POLL_INTERVAL_SECONDS` and any deadline for that, so polls never overlap (R4).
- Memory: `SOURCE_KIND=file` adds about 200 MB at peak for an 8 MiB file (measured in the source module). Document it for operators; `FileSource` is for demos and tests.

## Requests (to the coordinator)
- Dockerfile (task 4, not this module's path): add `COPY config/default-config.yaml /app/default-config.yaml`. Until then the image has no bundled default, and without a mount it fails with "no config file" (R21, `metrics/CLAUDE.md`).
