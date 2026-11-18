# Plan

Master plan: task list with **review phases** (below), then the detail of each task. Review rules live in `REVIEW.md`; agent roster in `docs/harness.md`.

## Tasks and status

| # | Task | Branch | Build | Review pipeline (R1-R6) | Status |
|---|---|---|---|---|---|
| 1 | shared contracts + mini fixture | `feat/contracts` | done | R1 done, R2/R3 catch-up done (findings planned), R4 skipped, R5 n/a, R6 done | merged `824c8b6`, v1.1.0; fix-up task 1b planned |
| 1b | review fix-ups: spec clarifications, contracts, fixture, config models, redact, plans (log rows 1-37) | `fix/phase-2-readiness` | built (gate green: 69 tests, `mypy src tests`) | R1 done; R2/R3 done twice (architect: ready with conditions, closed; security: 2 HIGH found and fixed); R6 pending | **blocks** 2a-2c until merged |
| 1c | ownership guardrails: path-guard hook, CI check tying contract changes to spec changes, CODEOWNERS | `feat/ownership-guard` | not started | R1-R3, R6 | before or alongside phase 2 |
| 2a | `state` | `feat/state` | not started | - | after 1b merges (plan: `specs/plans/state.md`) |
| 2b | `metrics` | `feat/metrics` | not started | - | after 1b merges (`specs/plans/metrics.md`) |
| 2c | `source` | `feat/source` | not started | - | after 1b merges (`specs/plans/source.md`) |
| 3 | `app` + e2e | `feat/app` | not started | R1-R6 incl. `fastapi-reviewer` and `verifier` | planned |
| 4 | tools and deployment: `check_config`, fixture-to-exposition golden test, Dockerfile run + default config + `APP_VERSION`, Quadlet, alert rules | `feat/deploy` | not started | R1-R3, R6, then phase review P4 | planned |
| 5 | `generate_config` (R22) | `feat/generate-config` | not started | R1-R4, R6 | planned |

## Review phases

### A. Per-task review pipeline (every task, in this order, before the PR is opened)

| Step | Who | What | Blocks merge if |
|---|---|---|---|
| R1 Gate | implementer, then CI | `ruff check`, `ruff format --check`, `mypy src tests`, `pytest -q`, `pip-audit`, `check_licenses.py`; output pasted in the PR | any failure (CI is authoritative; local runs are on 3.13 until 3.12 is confirmed) |
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
| P2 | Architecture review of module boundaries and contracts | before phase 2 starts | `architect` | **done: READY WITH CONDITIONS** (2026-11-19); all conditions closed in task 1b (log rows 29-37), not re-checked by the architect a third time; gate and boundary tests pass |
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
| 1 | python | MEDIUM | `mypy src tests` aborts (duplicate module `conftest`/`tests.conftest`) because `pythonpath` includes `.`; tests are not type-checked (CI runs `mypy src` only). Verified. | fixed: package markers; `mypy src tests` passes and CI now runs it |
| 2 | python, code | MEDIUM | `extract.extras` accepts duplicate `(scope, key)` entries; later one silently wins. Verified. | fixed: field validator, test with key path |
| 3 | code | MEDIUM | `state` cannot receive its retention: spec shows `BatteryHistory(store).update(...)` but R14 / `Tuning.state_retention_days` need a value | fixed in spec 3 and 8: `BatteryHistory(store, tuning)` |
| 4 | code | MEDIUM | Fixture lacks cases the spec needs: access point (`ACCESS_CONTROLLER_CHANNEL`), an OPEN/TILTED contact or room window, a same-type-in-one-room collision pair, an `extras` field for a golden test | fixed: 10 devices incl. access point, OPEN contact, `boostDuration` extras example; `collision_state` fixture |
| 5 | code | MEDIUM | Config validation thin: `ValveRule.fields` may omit `position_ratio` (my own test uses `{}`); contact rule may omit `window_state`; required top-level sections undocumented | fixed: rules must map `position_ratio` / `window_state`; field-level validators give key paths; missing required section tested |
| 6 | code | LOW | Tests partly tautological: field-name set copied from spec; protocol test does not check `fetch` is async; invalid-config test accepts any `ValidationError` and ignores the error location (R19 wants the path); no test loads the real default YAML (needs `config/default-config.yaml`, task 2b) | fixed: error-location tests, async check, key-pattern test, default config loaded into the models (`test_default_config.py`) |
| 7 | code | LOW | Frozen dataclasses holding a dict in `extras` are not hashable | fixed: docstring note and test |
| 8 | code | note | pydantic is imported directly but listed in the SBOM only via FastAPI | fixed: pydantic row in the SBOM dependency table |
| 9 | security | LOW | Capture tool keeps room/device names (by design, git-ignored, "review before committing"); `SGTIN_RE` is uppercase only; spec says the generator output has no names but the capture tool does not enforce it | fixed (regex now case-insensitive); names stay in the local capture by owner decision, owner to accept |
| 10 | security | LOW | Release job runs `npm install` with write permissions, unpinned plugin ranges and unpinned actions | open: CI follow-up (SHA pins, npm lockfile) |
| 11 | security | note | Base image `python:3.12-slim` is unpinned; a same-repo PR can change the workflow and use `DOCKERHUB_TOKEN` | open: pin base image digest with the Dockerfile task; token scope and branch protection are owner actions |
| 12 | architect | HIGH (process) | `check_config --fixture` and the fixture-to-exposition golden test (R20, spec 10) need `parse_snapshot`, but `metrics` may not import `source`; `check_config.py` has no owner | fixed in spec: `check_config` and the fixture golden test move to task 4 (tools may import every module); `metrics.render` takes a hand-built `Snapshot` |
| 13 | architect | HIGH (process) | Meta-metrics have two owners: spec 3 says `metrics` builds them in, the `app` row and `app/CLAUDE.md` say `app` owns them; one private `CollectorRegistry`; `data_age` cannot be hidden before the first success with `set_function` alone | fixed in spec 3: `metrics` owns meta and derived metrics; `record_success`/`record_error`; `data_age` absent before first success |
| 14 | architect | HIGH (process) | `specs/plan.md` is a single shared file; three parallel agents would conflict on it | fixed: `specs/plans/{state,metrics,source,app}.md`; `CLAUDE.md`, `specs/README.md`, implementer agent updated |
| 15 | architect | HIGH | No shared scrubbing function: `source` scrubs `UpstreamError` bodies, but `app` logs every other exception too (R15, spec 9) | fixed: `redact.py` + `test_redact.py` (third shared contract); `app` logging filter specified |
| 16 | architect | MEDIUM | Name-collision rule (fatal at startup, suffix later) does not fit `parse_snapshot`'s signature | fixed: `NameCollisionError`, `CollisionPolicy`, `parse_snapshot(..., on_collision)`; first successful poll = startup |
| 17 | architect | MEDIUM | `BatteryHistory` retention (also log row 3); return value, first sight while unreachable and `lowBat=None` undefined | fixed in spec 8: records returned for current devices only, first sight while unreachable, `None` handled |
| 18 | architect | MEDIUM | `create_app` takes four parameters but `uvicorn --factory` calls it with none; unclear if `app` imports concrete classes or protocols | fixed in spec 3: all `create_app` parameters optional with env defaults; concrete imports only in `app/wiring.py` |
| 19 | architect | MEDIUM | Shared test/config files: tests have no package markers (duplicate test names across `tests/<module>/` break collection, same root cause as log row 1); `source` and `metrics` both need `extract` defaults and could drift | fixed: package markers, `config/default-config.yaml` (`extract`, `tuning`), `default_extract`/`default_tuning` fixtures |
| 20 | architect | LOW | Naming: `ExtraField.scope` singular (`room`) vs metric `scope` plural (`rooms`); label-to-attribute mapping per scope unspecified | fixed: scope/label mapping table in spec 6.1 |
| 21 | architect | LOW | Files agents must not touch in phase 2 (`pyproject.toml`, `CLAUDE.md`, `Dockerfile`); spec 11 wrongly assigns a Dockerfile change to the metrics task | fixed: spec 12.1 rules, repeated in each module plan; Dockerfile change moved to task 4 |
| 22 | architect | process | Module ownership not enforced: no path guard hook, no CI check of changed paths per branch, no CODEOWNERS, no import-boundary check, nothing ties a contract change to a spec change | partly fixed: import-boundary test added; path-guard hook, CODEOWNERS and a CI check tying contract changes to spec changes remain (task 1c) |
| 23 | security (re-review of task 1b) | HIGH | `redact.scrub` leaked Python-repr credentials (`{'authToken': 'abc'}`) and bodies with single-quoted keys/values. Reproduced. | fixed: quote-aware pattern, test added |
| 24 | security (re-review) | HIGH | `Authorization: Basic <cred>` consumed only the scheme word; bare `Bearer <token>` not scrubbed. Reproduced. | fixed: any scheme word handled, standalone bearer rule (6+ characters), tests |
| 25 | security (re-review) | MEDIUM | Key coverage narrow (`auth_token`, `api_key`, `password`, `secret` unchanged) | fixed: broader key list incl. `access-token`, `passwd`, prefixed keys such as `my_token`; tests |
| 26 | security (re-review) | MEDIUM | Quoted values with spaces or escaped quotes were cut mid-value (`token: "abc def"` kept `def`) | fixed: full quoted-string match with escapes; tests |
| 27 | security (re-review) | LOW | SGTIN `\b` anchors missed underscore-adjacent IDs (`dev_<sgtin>`), also in `scripts/fixture/dump_state.py` | fixed in both places |
| 28 | security (re-review) | LOW | Not caught by design: a secret split across lines, fullwidth Unicode keys, bare bearer tokens under 6 characters; the `secrets=` argument covers known secrets exactly | accepted as residual risk (owner to confirm); no ReDoS (100 KB inputs under 20 ms) |
| 29 | architect (re-review of task 1b) | HIGH | No way to switch the collision policy: `Source.fetch()` took no argument; the warning had no owner; startup-fatal conflicted with R2 | fixed: `Source.fetch(on_collision)` in the contract; the source logs the warning; R2 and C1 define "startup" (first success) and exit non-zero on a collision before it |
| 30 | architect (re-review) | HIGH | `metrics/CLAUDE.md` stale and self-contradicting (agents load it automatically); `Gauge.set_function` cannot hide data age before the first success | fixed: file rewritten from spec 3; data age via a custom collector; root `CLAUDE.md`, R3 and 6.6 corrected |
| 31 | architect (re-review) | MEDIUM | `app` had no protocols to use; wiring-only rule not enforced; `plans/app.md` contradicted it | fixed: `app/ports.py` in spec 3 and the plan; import-boundary test enforces `app/wiring.py`-only imports and `tests/<module>` staying inside their module |
| 32 | architect (re-review) | MEDIUM | Two owners for config resolution (`load_config` and `app` both reading `CONFIG_FILE`) | fixed: `app` reads the env and passes `path`; `load_config(path: Path | None)` resolves and never reads the environment (R21, spec 3) |
| 33 | architect (re-review) | MEDIUM | Spec 8 contradicted itself (pruning needs last-seen; "save only on change"; create rules; unreachable counts as seen?) | fixed: spec 8 rewritten (`last_seen_day`, one extra write per day, creation and unreachable rules); `plans/state.md` updated |
| 34 | architect (re-review) | MEDIUM | `mini_state.json` had no protected owner (lived under `tests/source/`) | fixed: moved to `tests/fixtures/`, listed as do-not-edit in spec 12.1 |
| 35 | architect (re-review) | LOW | No version source for `homematic_exporter_build_info` | fixed: env `APP_VERSION` (default `dev`), set by the image build (task 4) |
| 36 | architect (re-review) | LOW | Import-boundary test scanned `src/` only | fixed: also scans `tests/<module>/` |
| 37 | architect (re-review) | LOW | Doc drift (plans/app.md, task numbering, `mypy src`, task 4 scope, `source/CLAUDE.md` httpx, root CLAUDE.md plan.md) | fixed |

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
| `tests/source/fixtures/mini_state.json` (moved to `tests/fixtures/` in task 1b) | new: hand-written, scrubbed fixture (3 rooms, 8 devices; 10 after task 1b) |
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
- Tasks 2a `state`, 2b `metrics`, 2c `source` (per-module plans in `specs/plans/`); then 3 `app` + e2e; then 4 tools and deployment; then 5 `generate_config`.
