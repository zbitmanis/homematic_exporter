# Plan: Task 3 - `app` module and e2e

- **Spec:** sections 3, 7, 9, 11, R1-R5, R15-R18
- **Branch:** `feat/app` (from merged `main`)
- **Depends on:** tasks 2a-2c merged (it wires the concrete `source`, `state` and `metrics` in `app/wiring.py` only)

## Files that change
| Path | Change |
|---|---|
| `src/homematic_exporter/app/` | `create_app(...)`, settings from env, `wiring.py` (only place importing concrete implementations), poll task in the lifespan, routes `/metrics` `/health` `/status`, logging filter built on `redact.scrub` |
| `src/homematic_exporter/app/ports.py` | local Protocols for the registry (`update`, `record_success`, `record_error`, `exposition`), battery history and config (`extract`, `tuning`) |
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

## Review pipeline (specs/plan.md)
- [ ] R1 gate  - [ ] R2 python-reviewer + fastapi-reviewer  - [ ] R3 security-reviewer  - [ ] R4 code-simplifier (optional)  - [ ] R6 owner PR review

## Requests (to the coordinator)
_none yet_
