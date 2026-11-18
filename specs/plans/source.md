# Plan: Task 2c - `source` module

- **Spec:** sections 3, 4, R15, C1, C7
- **Branch:** `feat/source` (from merged `main`)
- **Depends on:** shared contracts only

## Files that change
| Path | Change |
|---|---|
| `src/homematic_exporter/source/parser.py` | `parse_snapshot(raw, now, extract, on_collision)` per spec section 4 |
| `src/homematic_exporter/source/file_source.py` | `FileSource(path, extract)`; both implement `Source.fetch(on_collision)`; the source logs one WARNING per new collision (names only) |
| `src/homematic_exporter/source/cloud.py` | `CloudSource(access_point, token, timeout, extract)` over `homematicip` 2.23.1 `AsyncHome`; builds `UpstreamError` with a body scrubbed by `redact.scrub` |
| `tests/source/` | parser tests on the shared `tests/fixtures/mini_state.json` (+ `collision_state`; **do not edit the shared fixture**, request changes), `default_extract` fixture; `CloudSource` tests with a fake home object |

## Order of work
1. Parser tests (rooms, device-to-room joins, naming, collision modes, valves, contacts, extras, `None` handling, unmapped model), then `parse_snapshot`.
2. `FileSource` tests, then `FileSource`.
3. `CloudSource` against a fake; no network, no real credentials.

## Risks
- `CloudSource` cannot be verified live in this task (first live run is a later review phase P8).
- The library is GPL-3.0: do not copy its code.
- Never log the token, access point or SGTINs.

## Proof
gate output; parser golden `Snapshot` for the fixture.

## Rules (spec 12.1)
- Edit only `src/homematic_exporter/source/`, `tests/source/`, this plan.
- Do not edit contracts (`contracts.py`, `config_models.py`, `redact.py`), the spec, `pyproject.toml`, root `CLAUDE.md`, `Dockerfile`, `.github/`, `docs/`, `requirements*.txt`, `tests/conftest.py`. Put change requests under "Requests" and stop.
- Cross-module imports only `contracts`, `config_models`, `redact` (`tests/test_import_boundaries.py`).
- Tests first; paste gate output (`ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`).

## Review pipeline (specs/plan.md)
- [ ] R1 gate  - [ ] R2 python-reviewer  - [ ] R3 security-reviewer  - [ ] R4 code-simplifier (optional)  - [ ] R6 owner PR review

## Requests (to the coordinator)
_none yet_
