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

## Closing review task (mandatory, last task of this plan; specs/plan.md section A)
The PR is not opened until every step is done or marked n/a with a reason. Paste each verdict into the PR description. After any HIGH/CRITICAL fix the same reviewer re-checks.
- [ ] R1 Gate: `ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`, `pip-audit`, `check_licenses.py` (output pasted)
- [ ] R2 `python-reviewer`
- [ ] R3 `code-reviewer`
- [ ] R4 `security-reviewer`
- [ ] R5 `architect`: conditional: only if a contract change was requested or shared types touched
- [ ] R6 `code-simplifier` (after R2-R5 are clean; gate re-run)
- [ ] R7 `performance-optimizer`: conditional: registry update and exposition on a large snapshot
- [ ] R8 n/a: tests only (no app yet)
- [ ] R9 `doc-updater`: `CLAUDE.md`, module `CLAUDE.md`, SBOM manifest, spec catalogue in sync
- [ ] R10 owner PR review and squash merge

## Requests (to the coordinator)
_none yet_
