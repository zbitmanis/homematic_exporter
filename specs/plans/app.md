# Plan: Task 3 - `app` module and e2e

- **Spec:** sections 3, 7, 9, 11, R1-R5, R15-R18
- **Branch:** `feat/app` (from merged `main`)
- **Depends on:** shared contracts only

## Files that change
| Path | Change |
|---|---|
| `src/homematic_exporter/app/` | `create_app(...)`, settings from env, `wiring.py` (only place importing concrete implementations), poll task in the lifespan, routes `/metrics` `/health` `/status`, logging filter built on `redact.scrub` |
| `tests/app/`, `tests/e2e/` | fake `Source`; `SOURCE_KIND=file` e2e; restart with the same `STATE_DIR` |

## Order of work
1. App tests with fakes (loop survives errors, `/metrics` never calls the source, `/health` 503 when the task dies, clean shutdown, no secrets in logs), then the app.
2. E2E with the file source.

## Risks
- Starts only after tasks 2a-2c are merged.
- `uvicorn --factory` must work with no arguments.

## Proof
gate output, e2e output, `verifier` run.

## Rules (spec 12.1)
- Edit only `src/homematic_exporter/app/`, `tests/app/`, this plan.
- Do not edit contracts (`contracts.py`, `config_models.py`, `redact.py`), the spec, `pyproject.toml`, root `CLAUDE.md`, `Dockerfile`, `.github/`, `docs/`, `requirements*.txt`, `tests/conftest.py`. Put change requests under "Requests" and stop.
- Cross-module imports only `contracts`, `config_models`, `redact` (`tests/test_import_boundaries.py`).
- Tests first; paste gate output (`ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`).

## Review pipeline (specs/plan.md)
- [ ] R1 gate  - [ ] R2 python-reviewer + fastapi-reviewer  - [ ] R3 security-reviewer  - [ ] R4 code-simplifier (optional)  - [ ] R6 owner PR review

## Requests (to the coordinator)
_none yet_
