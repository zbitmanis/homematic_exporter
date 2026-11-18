# Plan

Master plan: task list with **review phases** (below), then the detail of each task. Review rules live in `REVIEW.md`; agent roster in `docs/harness.md`.

## Tasks and status

| # | Task | Branch | Build | Review pipeline (R1-R6) | Status |
|---|---|---|---|---|---|
| 1 | shared contracts + mini fixture | `feat/contracts` | done | R1 done, R2/R3 catch-up done (findings planned), R4 skipped, R5 n/a, R6 done | merged `824c8b6`, v1.1.0; fix-up task 1b planned |
| 1b | review fix-ups: spec clarifications, contracts, fixture, config models, plans (log rows 1-22) | `fix/phase-2-readiness` | planned | R1-R3, R6, then P2 re-review | next, **blocks** 2b and 2c |
| 2a | `state` | `feat/state` | not started | - | can start after row 17 is settled |
| 2b | `metrics` | `feat/metrics` | not started | - | next |
| 2c | `source` | `feat/source` | not started | - | next |
| 3 | `app` + e2e | `feat/app` | not started | R1-R6 incl. `fastapi-reviewer` and `verifier` | planned |
| 4 | Dockerfile run, Quadlet, alert rules | `feat/deploy` | not started | R1-R3, R6, then phase review P4 | planned |
| 5 | `generate_config` (R22) | `feat/generate-config` | not started | R1-R4, R6 | planned |

## Review phases

### A. Per-task review pipeline (every task, in this order, before the PR is opened)

| Step | Who | What | Blocks merge if |
|---|---|---|---|
| R1 Gate | implementer, then CI | `ruff check`, `ruff format --check`, `mypy src`, `pytest -q`, `pip-audit`, `check_licenses.py`; output pasted in the PR | any failure (CI is authoritative; local runs are on 3.13 until 3.12 is confirmed) |
| R2 Code review | `python-reviewer`; plus `fastapi-reviewer` for `app`; `code-reviewer` for cross-module diffs | correctness, types, async, spec match | any CRITICAL or HIGH |
| R3 Security review | `security-reviewer` | secrets, logs, config, state permissions, workflows, image | any CRITICAL or HIGH |
| R4 Simplify | `code-simplifier` (optional) | behavior-preserving clean-up after R2/R3 are clean; gate re-run | gate fails after the change |
| R5 Verify | `verifier` (and `e2e-runner` from task 3) | run the thing: `/metrics`, failure and restart behavior, no secrets in output | any failed check; **n/a** until an app exists |
| R6 Owner review | you | PR review; squash merge with a Conventional Commit title | your call |

Rules: the agent that wrote the code never reviews it; reviewers are read-only; findings are recorded in the task's review log (table below) with a status (open, fixed, accepted, rejected + reason); a finding is only "accepted" by the owner.

### B. Phase-level reviews

| ID | Review | When | Who | Status |
|---|---|---|---|---|
| P1 | Intent and spec review | before any code | owner (PRs) | **done** (intent accepted, spec merged) |
| P2 | Architecture review of module boundaries and contracts | before phase 2 starts | `architect` | **done: NOT READY**, 11 findings (log rows 12-22); re-review after task 1b |
| P3 | Phase-2 integration review | after `state`, `metrics`, `source` are merged, before `app` | `architect` + `code-reviewer`; golden parse-to-metrics test | planned |
| P4 | Security review before the first published working image | before the first release that contains a runnable app | `security-reviewer` + owner; secrets handling, image, workflows, live token handling | planned |
| P5 | Performance review | after `app` | `performance-optimizer`: poll duration, memory soak, series count | planned |
| P6 | Licensing and compliance review | before each release | owner + `check_licenses.py`, notices, SBOM | planned (partly automated) |
| P7 | Harness review | once an `evals/` suite exists, then periodically | `harness-optimizer` | blocked: no evals yet |
| P8 | First live run review | first run against the real access point | owner: compare exported values with the Homematic app | planned |

### C. Review status per task

| Task | R1 Gate | R2 Code | R3 Security | R4 Simplify | R5 Verify | R6 Owner |
|---|---|---|---|---|---|---|
| 1 contracts | pass (local 3.13; CI result not seen) | approve; 5 MEDIUM, 2 LOW | approve; 2 LOW | skipped | n/a | done |
| 2a state | - | - | - | - | n/a | - |
| 2b metrics | - | - | - | - | n/a | - |
| 2c source | - | - | - | - | n/a | - |
| 3 app | - | - | - | - | - | - |

### D. Review log

_Catch-up review of task 1 (merged `824c8b6`), 2026-11-19, run read-only by `python-reviewer`, `security-reviewer`, `code-reviewer` and `architect`. Verdicts: python-reviewer APPROVE, security-reviewer APPROVE, code-reviewer APPROVE (no CRITICAL or HIGH on the code); **architect: NOT READY for the parallel phase until the spec gaps below are closed** (state can start today; source and metrics after the fixes). "Verified" means I reproduced it myself. Status values: open, planned (fix scheduled), accepted (owner), rejected (reason)._

| # | Reviewer | Severity | Finding | Status |
|---|---|---|---|---|
| 1 | python | MEDIUM | `mypy src tests` aborts (duplicate module `conftest`/`tests.conftest`) because `pythonpath` includes `.`; tests are not type-checked (CI runs `mypy src` only). Verified. | planned: `explicit_package_bases` and decide whether the gate checks tests |
| 2 | python, code | MEDIUM | `extract.extras` accepts duplicate `(scope, key)` entries; later one silently wins. Verified. | planned: validator in `ExtractConfig` |
| 3 | code | MEDIUM | `state` cannot receive its retention: spec shows `BatteryHistory(store).update(...)` but R14 / `Tuning.state_retention_days` need a value | planned: spec change `BatteryHistory(store, retention_days: int)` before phase 2 |
| 4 | code | MEDIUM | Fixture lacks cases the spec needs: access point (`ACCESS_CONTROLLER_CHANNEL`), an OPEN/TILTED contact or room window, a same-type-in-one-room collision pair, an `extras` field for a golden test | planned: extend `mini_state.json` once, before the parallel tasks (parallel edits would conflict) |
| 5 | code | MEDIUM | Config validation thin: `ValveRule.fields` may omit `position_ratio` (my own test uses `{}`); contact rule may omit `window_state`; required top-level sections undocumented | planned: require the key attribute in each rule; document required sections in the spec |
| 6 | code | LOW | Tests partly tautological: field-name set copied from spec; protocol test does not check `fetch` is async; invalid-config test accepts any `ValidationError` and ignores the error location (R19 wants the path); no test loads the real default YAML (needs `config/default-config.yaml`, task 2b) | planned |
| 7 | code | LOW | Frozen dataclasses holding a dict in `extras` are not hashable | planned: note in `contracts.py` docstring and in module `CLAUDE.md` files |
| 8 | code | note | pydantic is imported directly but listed in the SBOM only via FastAPI | planned: add a direct row to the SBOM dependency table (already pinned in `requirements.txt`) |
| 9 | security | LOW | Capture tool keeps room/device names (by design, git-ignored, "review before committing"); `SGTIN_RE` is uppercase only; spec says the generator output has no names but the capture tool does not enforce it | proposed: make the regex case-insensitive now; names stay in the local capture (owner decision on 2026-11-18); owner to accept |
| 10 | security | LOW | Release job runs `npm install` with write permissions, unpinned plugin ranges and unpinned actions | open: known (TODO pin by SHA, commit an npm lockfile); belongs to the CI follow-up |
| 11 | security | note | Base image `python:3.12-slim` is unpinned; a same-repo PR can change the workflow and use `DOCKERHUB_TOKEN` | open: pin by digest with the Dockerfile task; scoped token and branch protection are owner actions |
| 12 | architect | HIGH (process) | `check_config --fixture` and the fixture-to-exposition golden test (R20, spec 10) need `parse_snapshot`, but `metrics` may not import `source`; `check_config.py` has no owner | planned: `metrics` exposes `render(config, snapshot) -> bytes` and tests with a hand-built `Snapshot`; `check_config` and the fixture golden test move to task 4 with `generate_config` (tool modules may import every module) |
| 13 | architect | HIGH (process) | Meta-metrics have two owners: spec 3 says `metrics` builds them in, the `app` row and `app/CLAUDE.md` say `app` owns them; one private `CollectorRegistry`; `data_age` cannot be hidden before the first success with `set_function` alone | planned: `metrics` owns them; add `Registry.record_success(ts, duration)` and `Registry.record_error()` to the interface; define the hidden-until-first-success behavior |
| 14 | architect | HIGH (process) | `specs/plan.md` is a single shared file; three parallel agents would conflict on it | planned: per-module plans in `specs/plans/<module>.md`; update `CLAUDE.md` workflow and `specs/README.md` |
| 15 | architect | HIGH | No shared scrubbing function: `source` scrubs `UpstreamError` bodies, but `app` logs every other exception too (R15, spec 9) | planned: pure shared `redact.py` with `scrub(text, secrets)` as a third contract; `app` adds a logging filter that uses it |
| 16 | architect | MEDIUM | Name-collision rule (fatal at startup, suffix later) does not fit `parse_snapshot`'s signature | planned: `NameCollisionError` in `contracts.py` and an `on_collision: Literal["error","suffix"]` parameter; `app` treats the first successful poll as startup |
| 17 | architect | MEDIUM | `BatteryHistory` retention (also log row 3); return value, first sight while unreachable and `lowBat=None` undefined | planned: `BatteryHistory(store, tuning)`; spec defines records returned (current devices only, R8), the unreachable and `None` cases |
| 18 | architect | MEDIUM | `create_app` takes four parameters but `uvicorn --factory` calls it with none; unclear if `app` imports concrete classes or protocols | planned: all parameters get env-derived defaults; state that `app` imports concrete `source` and `metrics` (wiring), depends on protocols for tests |
| 19 | architect | MEDIUM | Shared test/config files: tests have no package markers (duplicate test names across `tests/<module>/` break collection, same root cause as log row 1); `source` and `metrics` both need `extract` defaults and could drift | planned: package markers or `--import-mode=importlib`; land the `extract`/`tuning` default config and a `default_extract` fixture in `tests/conftest.py` before phase 2 |
| 20 | architect | LOW | Naming: `ExtraField.scope` singular (`room`) vs metric `scope` plural (`rooms`); label-to-attribute mapping per scope unspecified | planned: one mapping table in spec 6.1 |
| 21 | architect | LOW | Files agents must not touch in phase 2 (`pyproject.toml`, `CLAUDE.md`, `Dockerfile`); spec 11 wrongly assigns a Dockerfile change to the metrics task | planned: rule in the module plans; requests go in the plan for the `app` task; fix spec 11 |
| 22 | architect | process | Module ownership not enforced: no path guard hook, no CI check of changed paths per branch, no CODEOWNERS, no import-boundary check, nothing ties a contract change to a spec change | planned: import-boundary test (no new dependency), path-guard hook, CODEOWNERS; contract changes go in their own small PR merged first |

Clean results worth keeping: capture file not tracked and not in the image; no secrets, SGTINs or tokens in git history; workflows use `pull_request` (no secrets for forks) and no untrusted text in `run:`; contracts and config models match spec sections 3 and 5.1 field for field; the fixture mirrors the real structure.

---

# Task 1 - shared contracts and test fixture

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
