# Plan: Task 2b - `metrics` module

- **Spec:** sections 3, 5.1, 6, R6-R10, R19-R21, C11
- **Branch:** `feat/metrics` (from merged `main`)
- **Depends on:** shared contracts only

## Files that change
| Path | Change |
|---|---|
| `src/homematic_exporter/metrics/config.py` | `AppConfig` (composes `Tuning`, `ExtractConfig`, metric definitions), `load_config(path: Path | None = None)` with the R21 resolution (explicit path must exist; `None` = mount path then bundled default; never reads the environment), startup validation errors with key paths (R19) |
| `src/homematic_exporter/metrics/registry.py` | `Registry.build/update/record_success/record_error/exposition`, `render(config, snapshot, batteries)`; private `CollectorRegistry`; series removal; derived (6.5) and meta (6.6) metrics; `data_age` absent before first success |
| `config/default-config.yaml` | **only the `metrics:` list** (spec 6.2-6.4); `extract`/`tuning` are fixed |
| `tests/metrics/` | hand-built `Snapshot` golden exposition, validation errors, extras-only metric, fallback order |

## Order of work
1. Validation tests for every R19 error class (with key path), then `load_config`.
2. Registry tests with a hand-built `Snapshot` (scale, transforms, series removal, `None` handling, cardinality), then `Registry`.
3. Fill the `metrics:` list and add the golden exposition file.

## Risks
- The integration golden test (fixture through the parser) is **not** this task (task 4).
- A raw-field typo silently produces no series (C11): log a warning for a metric with zero series on two consecutive updates.

## Proof
gate output plus a golden exposition file reviewed by the owner.

## Rules (spec 12.1)
- Edit only `src/homematic_exporter/metrics/`, `tests/metrics/`, this plan, and the `metrics:` list of `config/default-config.yaml`.
- Do not edit contracts (`contracts.py`, `config_models.py`, `redact.py`), the spec, `pyproject.toml`, root `CLAUDE.md`, `Dockerfile`, `.github/`, `docs/`, `requirements*.txt`, `tests/conftest.py`. Put change requests under "Requests" and stop.
- Cross-module imports only `contracts`, `config_models`, `redact` (`tests/test_import_boundaries.py`).
- Tests first; paste gate output (`ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`).

## Review pipeline (specs/plan.md)
- [ ] R1 gate  - [ ] R2 python-reviewer  - [ ] R3 security-reviewer  - [ ] R4 code-simplifier (optional)  - [ ] R6 owner PR review

## Requests (to the coordinator)
_none yet_
