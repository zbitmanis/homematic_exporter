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
2. Battery tests following spec section 8 exactly (record created on first sight for every device, first sight low vs unreachable vs `None`, transitions, unreachable freeze but still seen, `last_seen_day` at day granularity with at most one extra write per day, prune by `tuning.state_retention_days`, returns only current devices, restart reload), then `BatteryHistory`.

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

## Closing review task (mandatory, last task of this plan; specs/plan.md section A)
The PR is not opened until every step is done or marked n/a with a reason. Paste each verdict into the PR description. After any HIGH/CRITICAL fix the same reviewer re-checks.
- [x] R1 Gate: `ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`, `pip-audit`, `check_licenses.py` (output pasted)
- [ ] R2 `python-reviewer`
- [ ] R3 `code-reviewer`
- [ ] R4 `security-reviewer`
- [ ] R5 `architect`: conditional: only if a contract change was requested or shared types touched
- [ ] R6 `code-simplifier` (after R2-R5 are clean; gate re-run)
- [ ] R7 `performance-optimizer`: conditional: n/a unless a hot path appears
- [ ] R8 n/a: tests only (no app yet)
- [ ] R9 `doc-updater`: `CLAUDE.md`, module `CLAUDE.md`, SBOM manifest, spec catalogue in sync
- [ ] R10 owner PR review and squash merge

## Requests (to the coordinator)
_none yet_
