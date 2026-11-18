# Plan: Task 2a - `state` module

- **Spec:** sections 3, 8, R12-R14, C3, C4
- **Branch:** `feat/state` (from merged `main`)
- **Depends on:** shared contracts only

## Files that change
| Path | Change |
|---|---|
| `src/homematic_exporter/state/store.py` | `FileStateStore(dir)`: 0700 dir, 0600 files, atomic write, refuses looser permissions |
| `src/homematic_exporter/state/battery.py` | `BatteryHistory(store, tuning)` with `update(devices, now) -> list[BatteryRecord]` |
| `src/homematic_exporter/state/__init__.py` | exports |
| `tests/state/` | `tmp_path` tests |

## Order of work
1. Store tests (permissions, atomicity, missing/corrupt file), then store.
2. Battery transition tests (first sight low, false to true, true to false, unreachable freeze, first sight while unreachable, `low_battery=None`, restart reload, prune by `tuning.state_retention_days`, returns only current devices), then `BatteryHistory`.

## Risks
- A corrupt state file must not crash the poll loop: decide and test (log and start empty).
- Time is injected (`now`), never read inside the class.

## Proof
gate output plus the transition table covered by tests; no secrets or paths in exceptions.

## Rules (spec 12.1)
- Edit only `src/homematic_exporter/state/`, `tests/state/`, this plan.
- Do not edit contracts (`contracts.py`, `config_models.py`, `redact.py`), the spec, `pyproject.toml`, root `CLAUDE.md`, `Dockerfile`, `.github/`, `docs/`, `requirements*.txt`, `tests/conftest.py`. Put change requests under "Requests" and stop.
- Cross-module imports only `contracts`, `config_models`, `redact` (`tests/test_import_boundaries.py`).
- Tests first; paste gate output (`ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`).

## Review pipeline (specs/plan.md)
- [ ] R1 gate  - [ ] R2 python-reviewer  - [ ] R3 security-reviewer  - [ ] R4 code-simplifier (optional)  - [ ] R6 owner PR review

## Requests (to the coordinator)
_none yet_
