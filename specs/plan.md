# Plan: Task 1 - shared contracts and test fixture

- **Spec:** `specs/spec.md` sections 3, 4, 5.1 (R6, R19)
- **Branch:** `feat/contracts` (from merged `main`)
- **Owner:** human-reviewed first; every other module task depends on it

## Files that change
| File | Change |
|---|---|
| `src/homematic_exporter/contracts.py` | new: `Room`, `Device`, `Valve`, `Contact`, `Snapshot`, `BatteryRecord`, `Extras`, `UpstreamError`, `Source`, `StateStore` (spec 3) |
| `src/homematic_exporter/config_models.py` | new: `ExtractConfig`, `ValveRule`, `ContactRule`, `ExtraField`, `Tuning` (spec 5.1), strict (`extra=forbid`, frozen) |
| `src/homematic_exporter/{__init__,source/,state/,metrics/,app/}__init__.py` | new: package skeleton so module branches do not conflict |
| `tests/source/fixtures/mini_state.json` | new: hand-written, scrubbed fixture (3 rooms, 8 devices) |
| `tests/conftest.py`, `tests/test_contracts.py`, `tests/test_config_models.py`, `tests/test_mini_fixture.py` | new tests |
| `pyproject.toml` | pytest `pythonpath` adds `.`; asyncio fixture loop scope set |
| `specs/spec.md`, `CLAUDE.md`, `REVIEW.md`, `docs/sbom/components.md` | `config_models.py` recorded as the second shared contract |

## Order of work (done in this order)
1. Mini fixture and its consistency tests (tests first).
2. Contract tests, then `contracts.py`.
3. Config-model tests, then `config_models.py`.
4. Gate, docs, commit.

## Decisions and spec correction
- **Spec gap found:** `parse_snapshot(..., extract: ExtractConfig)` needs a type that `source` may import, but the spec gave the config schema to `metrics` and forbids cross-module imports. Resolution: `ExtractConfig` and `Tuning` live in a shared `config_models.py` (a contract like `contracts.py`); `metrics` still owns loading and the metric-definition schema. Spec section 3 updated.
- Config models use pydantic (already a runtime dependency via FastAPI), so strict validation errors with key paths (R19) come for free.
- `Source`/`StateStore` are `runtime_checkable` so `app` wiring tests can assert conformance.
- `StateStore` values are `dict[str, object]` (JSON-like), not `Any`.

## Risks
- Contract churn: later modules may need a field. Mitigation: any change is a spec change in the same commit; the contracts are small.
- The fixture is hand-written, so it can drift from the real API. Mitigation: it mirrors the real field names and channel structure of the capture (checked field by field), and the local capture stays the reference for periodic comparison.
- Pins were resolved on Python 3.13; this gate ran on 3.13, CI runs 3.12.

## Proof
`ruff check .`, `ruff format --check .`, `mypy src` (strict), `pytest -q` (21 tests), `python scripts/check_licenses.py`: all pass locally (Python 3.13 venv). CI gate on the PR runs the same on 3.12.

## Next tasks (separate plan entries, can start in parallel after this merges)
- Task 2a `source`, 2b `state`, 2c `metrics`; then 3 `app`; then 4 e2e/Dockerfile/Quadlet/alerts; then 5 `generate_config`.
