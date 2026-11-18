# Plan

Master plan: task list with the **closing review task** every plan ends with and the phase-level reviews (below), then the detail of each task. Review rules live in `REVIEW.md`; agent roster in `docs/harness.md`.

## Tasks and status

| # | Task | Branch | Build | Closing review task (R1-R10, section A) | Status |
|---|---|---|---|---|---|
| 1 | shared contracts + mini fixture | `feat/contracts` | done | partly: see section C | merged `824c8b6`, v1.1.0 |
| 1b | review fix-ups: spec clarifications, contracts, fixture, config models, redact, plans (log rows 1-37) | `fix/phase-2-readiness` | done (gate green: 69 tests, `mypy src tests`) | incomplete: R2, R3, R6, R9 not run, `redact.py` fixes not re-checked (section C) | merged (#5) |
| 1b-close | catch-up of the missing closing reviews for tasks 1 and 1b: `python-reviewer`, `code-reviewer`, `code-simplifier`, `doc-updater` (docs check), security re-check of `redact.py` | `fix/1b-closing-review` | done (gate green: 225 tests) | all steps done, findings fixed or accepted (rows 59-75), final security re-check clean | planned, **before phase 2** |
| 1c | ownership guardrails: `ownership.yaml`, CI check, path-guard hook, worktree helper (CODEOWNERS dropped: no value on a solo repo) | `feat/ownership-guard` | done | closing review plus re-check done; all findings fixed or accepted (rows 38-58) | merged (`c49544a`) |
| 2a | `state` | `feat/state` | not started | all applicable steps (section A matrix) | after 1b merges (plan: `specs/plans/state.md`) |
| 2b | `metrics` | `feat/metrics` | not started | all applicable steps (section A matrix) | after 1b merges (`specs/plans/metrics.md`) |
| 2c | `source` | `feat/source` | not started | all applicable steps (section A matrix) | after 1b merges (`specs/plans/source.md`) |
| 3 | `app` + e2e | `feat/app` | not started | all steps incl. `fastapi-reviewer`, `verifier`, `e2e-runner`, `performance-optimizer` | planned |
| 4 | tools and deployment: `check_config`, fixture-to-exposition golden test, Dockerfile run + default config + `APP_VERSION`, Quadlet, alert rules | `feat/deploy` | not started | all steps, then phase review P4 | planned |
| 5 | `generate_config` (R22) | `feat/generate-config` | not started | R1-R6, R8-R10 | planned |

## Review phases

### A. Closing review task (the mandatory last task of every plan)

Every task plan, including every module plan in `specs/plans/`, ends with this closing task. **The PR is not opened until it is complete**; a step may be marked n/a only with the reason in the PR. The PR description lists the result of every step (reviewer verdict, finding counts, gate output). Unresolved CRITICAL or HIGH findings block the PR; the owner accepts any residual item explicitly (review log).

| Step | Who | What | Blocks the PR if |
|---|---|---|---|
| R1 Gate | implementer, then CI | `ruff check`, `ruff format --check`, `mypy src tests`, `pytest -q`, `pip-audit`, `check_licenses.py`; output pasted | any failure (CI is authoritative; local runs are on 3.13 until 3.12 is confirmed) |
| R2 Python review | `python-reviewer`; `fastapi-reviewer` for `app` | idioms, types, async, spec match | CRITICAL or HIGH |
| R3 Code review | `code-reviewer` | diff against spec and plan, tests meaningful, contract gaps | CRITICAL or HIGH |
| R4 Security review | `security-reviewer` | secrets, logs, config, state permissions, workflows, image; try to break scrubbing or parsing | CRITICAL or HIGH |
| R5 Architecture review | `architect` | module boundaries, contracts, shared files, merge-order hazards | not ready / HIGH |
| R6 Simplify | `code-simplifier` | behavior-preserving clean-up after R2-R5 are clean; gate re-run | gate fails afterwards |
| R7 Performance review | `performance-optimizer` | poll cost, event-loop blocking, memory, series count, image size | a regression against the spec targets |
| R8 Verify | `verifier` (run the thing); `e2e-runner` (failure, restart, container) | `/metrics`, failure and restart behavior, no secrets in output | any failed check |
| R9 Docs in sync | `doc-updater` | `CLAUDE.md`, module `CLAUDE.md`, SBOM manifest, spec catalogue, harness doc match the change | stale or contradicting docs |
| R10 Owner review | you | PR review; squash merge with a Conventional Commit title | your call |

Rules: the agent that wrote the code never reviews it; reviewers are read-only; after a fix for a HIGH or CRITICAL finding the same reviewer re-checks it; findings go in the review log (table D) with a status (open, fixed, accepted, rejected + reason); only the owner can mark a finding accepted.

**Which steps apply to which task** (R = required, C = conditional, n/a = not applicable; the reason is written in the PR):

| Step | 2a `state`, 2b `metrics`, 2c `source` | 3 `app` + e2e | 4 tools + deploy | 5 `generate_config` | 1c ownership guardrails |
|---|---|---|---|---|---|
| R1 Gate | R | R | R | R | R |
| R2 Python (+ FastAPI) | R | R (+ `fastapi-reviewer`) | R | R | R for any Python |
| R3 Code | R | R | R | R | R |
| R4 Security | R | R | R | R | R (hooks run commands) |
| R5 Architecture | C (R if a contract change was requested or shared types touched) | R | R | C | R |
| R6 Simplify | R | R | R | R | n/a |
| R7 Performance | C (parser and registry hot paths) | R | R (image size, start-up) | n/a | n/a |
| R8 Verify | n/a (tests only) | R (`verifier` + `e2e-runner`) | R (`verifier` + `e2e-runner`) | R (`verifier` on the fixture) | R (`verifier` triggers a violating edit) |
| R9 Docs | R | R | R | R | R |
| R10 Owner | R | R | R | R | R |

Harness changes (`.claude/`, hooks, agents) additionally get `harness-optimizer` once an `evals/` suite exists (phase review P7).

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

### C. Review status per task (R1 Gate, R2 Python, R3 Code, R4 Security, R5 Architecture, R6 Simplify, R7 Performance, R8 Verify, R9 Docs, R10 Owner)

| Task | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 contracts | pass (3.13) | approve (catch-up) | approve (catch-up) | approve (catch-up) | not ready, fixed in 1b | skipped | n/a | n/a | n/a | merged |
| 1b readiness | pass (3.13) | warning, fixed (1b-close) | approve, doc fixes (1b-close) | 2 HIGH fixed and confirmed; 1 new HIGH found and fixed (1b-close) | done: ready with conditions, conditions closed | done: 1 test move (1b-close) | n/a | n/a | docs check done, fixed (1b-close) | merged (#5) |
| 1c guardrails | pass (3.13) | BLOCK then re-check: all fixed | WARNING, fixed | 5 bypasses then re-check: all fixed, 1 accepted design gap | ready with conditions, fixed | n/a | n/a | done by hand (hook + 6 CI scenarios) | checked, fixed | pending |
| 2a state | - | - | - | - | C | - | C | n/a | - | - |
| 2b metrics | - | - | - | - | C | - | C | n/a | - | - |
| 2c source | - | - | - | - | C | - | C | n/a | - | - |
| 3 app | - | - | - | - | - | - | - | - | - | - |
| 4 tools + deploy | - | - | - | - | - | - | - | - | - | - |
| 5 generate_config | - | - | - | - | C | - | n/a | - | - | - |

Gaps in the closed tasks were real: task 1b was merged without `python-reviewer`, `code-reviewer`, `code-simplifier` and `doc-updater`, and without a re-check of the `redact.py` fixes. Task `1b-close` closed all of them except the simplifier step (rows 59-71).

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
| 22 | architect | process | (superseded by task 1c, rows 38-52) Module ownership not enforced: no path guard hook, no CI check of changed paths per branch, no CODEOWNERS, no import-boundary check, nothing ties a contract change to a spec change | partly fixed: import-boundary test added; path-guard hook, CODEOWNERS and a CI check tying contract changes to spec changes remain (task 1c) |
| 23 | security (re-review of task 1b) | HIGH | `redact.scrub` leaked Python-repr credentials (`{'authToken': 'abc'}`) and bodies with single-quoted keys/values. Reproduced. | fixed: quote-aware pattern, test added |
| 24 | security (re-review) | HIGH | `Authorization: Basic <cred>` consumed only the scheme word; bare `Bearer <token>` not scrubbed. Reproduced. | fixed: any scheme word handled, standalone bearer rule (6+ characters), tests |
| 25 | security (re-review) | MEDIUM | Key coverage narrow (`auth_token`, `api_key`, `password`, `secret` unchanged) | fixed: broader key list incl. `access-token`, `passwd`, prefixed keys such as `my_token`; tests |
| 26 | security (re-review) | MEDIUM | Quoted values with spaces or escaped quotes were cut mid-value (`token: "abc def"` kept `def`) | fixed: full quoted-string match with escapes; tests |
| 27 | security (re-review) | LOW | SGTIN `\b` anchors missed underscore-adjacent IDs (`dev_<sgtin>`), also in `scripts/fixture/dump_state.py` | fixed in both places |
| 28 | security (re-review) | LOW | Not caught by design: a secret split across lines, fullwidth Unicode keys, bare bearer tokens under 6 characters; the `secrets=` argument covers known secrets exactly | **accepted by owner (2026-11-19)** as residual risk; no ReDoS (100 KB inputs under 20 ms) |
| 29 | architect (re-review of task 1b) | HIGH | No way to switch the collision policy: `Source.fetch()` took no argument; the warning had no owner; startup-fatal conflicted with R2 | fixed: `Source.fetch(on_collision)` in the contract; the source logs the warning; R2 and C1 define "startup" (first success) and exit non-zero on a collision before it |
| 30 | architect (re-review) | HIGH | `metrics/CLAUDE.md` stale and self-contradicting (agents load it automatically); `Gauge.set_function` cannot hide data age before the first success | fixed: file rewritten from spec 3; data age via a custom collector; root `CLAUDE.md`, R3 and 6.6 corrected |
| 31 | architect (re-review) | MEDIUM | `app` had no protocols to use; wiring-only rule not enforced; `plans/app.md` contradicted it | fixed: `app/ports.py` in spec 3 and the plan; import-boundary test enforces `app/wiring.py`-only imports and `tests/<module>` staying inside their module |
| 32 | architect (re-review) | MEDIUM | Two owners for config resolution (`load_config` and `app` both reading `CONFIG_FILE`) | fixed: `app` reads the env and passes `path`; `load_config(path: Path | None)` resolves and never reads the environment (R21, spec 3) |
| 33 | architect (re-review) | MEDIUM | Spec 8 contradicted itself (pruning needs last-seen; "save only on change"; create rules; unreachable counts as seen?) | fixed: spec 8 rewritten (`last_seen_day`, one extra write per day, creation and unreachable rules); `plans/state.md` updated |
| 34 | architect (re-review) | MEDIUM | `mini_state.json` had no protected owner (lived under `tests/source/`) | fixed: moved to `tests/fixtures/`, listed as do-not-edit in spec 12.1 |
| 35 | architect (re-review) | LOW | No version source for `homematic_exporter_build_info` | fixed: env `APP_VERSION` (default `dev`), set by the image build (task 4) |
| 36 | architect (re-review) | LOW | Import-boundary test scanned `src/` only | fixed: also scans `tests/<module>/` |
| 37 | architect (re-review) | LOW | Doc drift (plans/app.md, task numbering, `mypy src`, task 4 scope, `source/CLAUDE.md` httpx, root CLAUDE.md plan.md) | fixed |
| 38 | python (task 1c) | HIGH | CI diff hides the source side of renames (`git mv` out of a protected path shows only the allowed destination) | fixed: `--no-renames -z`; tests incl. a contract rename |
| 39 | python (task 1c) | HIGH | Restricted YAML parser silently mis-parsed valid YAML (inline comments, quoted commas, same-indent lists, booleans, tabs) | fixed: strict parser raising `ValueError`, `validate_config`, 10 negative tests |
| 40 | python, code, security, architect | MEDIUM | Branch names that merely look like a module (`feat/state2`, `chore/state`, `Feat/state`) fell back to unrestricted | fixed: every branch must be `feat/` or `fix/`; lookalikes fail; owner's existing branches still pass |
| 41 | python, security | MEDIUM | CI script crashed or skipped on missing files or a bad base ref (a bad ref counted as "no rules") | fixed: base must resolve; skip only for the explicit bootstrap; missing file on either side handled |
| 42 | python, security | MEDIUM | Hook resolved relative paths against its own cwd and took the root from the payload cwd (`cwd=/` or another repo fail-opened) | fixed: root from the hook's own location, relative paths against payload cwd |
| 43 | security, architect | HIGH | CI ran the PR's own checker code; a PR could replace it | fixed in `ci.yml`: the base branch's copies of the checker and library are run; the job also fails if the base cannot be resolved. Residual: a PR can edit `ci.yml` itself; a required status check named `ownership` stops the merge if the job disappears (owner action) |
| 44 | architect | MEDIUM | "Contract change may not touch module code" would deadlock the first breaking contract change | fixed: spec rule stays, module code in the same PR is allowed but warned about |
| 45 | architect, security | MEDIUM | Hook allowed edits outside the worktree (sibling checkouts, case-variant roots, symlink escapes) | fixed: blocked for module agents except temp dirs; symlink targets checked; case-insensitive comparison by file identity; fails closed for module agents |
| 46 | code, architect, python | LOW | `default-config.yaml` rule was a deny-list (new top-level keys unchecked) | fixed: allow-list `editable_sections: [metrics]` |
| 47 | architect | LOW | Worktree helper could only create `feat/<module>` | fixed: optional validated branch argument |
| 48 | python | LOW | Trailing-slash and malformed globs matched nothing silently; test gaps | fixed: `validate_config`, glob tests for `**`, special characters |
| 49 | code, docs check | MEDIUM | Docs still described the unguarded setup (`claude --worktree`), "Was:" leftovers, CODEOWNERS silently dropped, evals in present tense, `check_config` shown as existing | fixed in `CLAUDE.md`, `harness.md`, `plan.md`, agents, `.claude/README.md`, module `CLAUDE.md` files, `components.md`, spec 12.1 |
| 50 | architect | note | `parse_simple_yaml` exists only so the hook runs without PyYAML; JSON would remove it | owner decision kept YAML; parser is now strict and tested |
| 51 | security | accepted limit | Bash edits (`sed -i`, `rm .hmx-module`) are invisible to the hook | documented; CI is the backstop |
| 52 | security | note | PRs from forks choose their own head branch name | solo repo; owner review; branch must match the scheme |
| 53 | python (re-check) | MEDIUM | Strict parser still mis-read valid YAML (apostrophe in a plain scalar, `\n`/unicode escapes, `yes/no/on`, signed and float numbers, `{}`/anchors/tags, Unicode digits, empty flow items, quoted keys) | fixed: values are limited to quoted strings (only `\"` and `\\` escapes), ASCII integers, `true`/`false` and simple plain words; everything else raises; keys must be plain; parity test against PyYAML on the supported subset, 35 negative cases |
| 54 | python (re-check) | MEDIUM | Two tests depended on the developer's machine (`$HOME` under a temp dir) | fixed: fixed non-temp path |
| 55 | python (re-check) | LOW | `a/***` accepted; lint nits in the hook | fixed: segment-wise `**` rule; hook lines wrapped |
| 56 | security (re-check) | MEDIUM | The hook's temp-dir allowance let a module agent write into a sibling worktree that lives under /tmp (also via a symlink) | fixed: temp paths inside any checkout (marker or ownership file above them) are not allowed; tests incl. symlink |
| 57 | security (re-check) | MEDIUM/LOW | A misspelled or quoted key in `ownership.yaml` (`module:`, `contract_file:`, `"config/default-config.yaml":`) silently dropped rules | fixed: `validate_config` rejects unknown top-level keys, an empty `modules` and malformed `editable_sections`; quoted keys already rejected by the parser |
| 58 | security (re-check) | residual design gap | Module identity comes from the branch name the author picks: a module agent that names its branch `feat/foo` is a coordinator branch to CI; only the hook (marker file) and convention stop it. A PR that edits `ci.yml` itself is protected only by a required status check named `ownership` plus review of `.github/**` | **accepted by design** for a solo repo (owner review is the backstop); turn on the required check in branch protection |
| 59 | security (1b-close) | HIGH | `redact.scrub` missed camelCase compound keys: `clientAuthToken` (a real Homematic field), `userPassword`, `password_hash`, `secret_key` | fixed: keys are scanned linearly and judged in code (credential word anywhere in the normalized key); tests |
| 60 | security (1b-close) | MEDIUM | URL-encoded keys and separators (`auth%5Ftoken%3Dabc`) not scrubbed | fixed: percent-encoded bytes allowed in keys, `%3D` as separator |
| 61 | security (1b-close) | MEDIUM | `Cookie:`/`Set-Cookie:` header lines and `Authorization: Digest ...` parameters only partly redacted | fixed: whole header line redacted for unquoted values |
| 62 | security (1b-close) | MEDIUM | `secrets=` matched only the exact raw string (not URL-encoded, form-encoded, base64 or other case) | fixed: variants of each secret, case-insensitive |
| 63 | security (1b-close) | LOW | `PIN 123456` / `PIN is 123456` in prose | fixed: bare PIN digits rule |
| 64 | python (1b-close) | MEDIUM | Unterminated quoted value (`token = "abc...` in a truncated body) leaked | fixed: unterminated quote redacted to the end of the line |
| 65 | python (1b-close) | MEDIUM | Unquoted multi-word values only partly redacted | accepted as a documented limit (a value ends at whitespace; quote values with spaces); pinned by a test and stated in the module docstring |
| 66 | python (1b-close) | LOW | Frozen config models still hold mutable dicts; `runtime_checkable` checks names only; weak tests (longest-first, idempotence, timing) | fixed: docstring notes; exact-output and corpus tests; timing test covers eight pathological shapes |
| 67 | own test (1b-close) | HIGH (found during the fix) | First version of the compound-key regex was quadratic (a 100 KB `tokentoken...` took 73 s) | fixed: linear scan with the credential decision in code; all pathological inputs under 0.1 s |
| 68 | code (1b-close) | MEDIUM | Stale text: protocol block in spec 3 and `source/CLAUDE.md`, `components.md` still showed `fetch()` without `on_collision`; fixture path `tests/source/fixtures/`; no plumbing for `APP_VERSION` | fixed: `fetch(on_collision)` everywhere; shared fixtures named; `Registry.build/render(..., version)`, `app` reads `APP_VERSION` |
| 69 | code (1b-close) | LOW | `app/CLAUDE.md` said "contract protocols" (should be local `app/ports.py`); spec diagram showed `parse_snapshot(raw)` | fixed |
| 70 | docs check (1b-close) | MEDIUM | `mypy src` in six agent files; contract lists naming only `contracts.py`; `harness.md` env names, `cosign`, `go.mod`, Makefile, deploy paths; `state/CLAUDE.md` "imports nothing"; `components.md` pydantic and package counts; `docs/ci/README.md` caveat; `CLAUDE.md` run/e2e commands for code that does not exist yet | fixed or marked planned |
| 71 | security (1b-close) | accepted limits | Not caught by design: keyword with no separator (`Token abc123`), plural keys with list values, bare JWT/base64/hex without key or `Bearer`; `dashed ACCESSPOINT-ID` forms; over-redaction is accepted | documented in the module docstring; the `secrets=` argument covers known secrets in raw, URL-encoded, form-encoded and base64 form (owner to confirm) |
| 72 | security (final re-check) | - | All earlier findings (rows 59-63) re-run: FIXED; no regressions in the scan (credential after a non-credential pair, quoted string containing `token=...`, status and message words survive) | confirmed |
| 73 | security (final re-check) | MEDIUM | Key names not treated as credentials: `private_key`, `access_key`, `sessionid`, `passphrase`, `credential`; a key with a space (`api key=abc`) and bare `key=` | fixed for the named keys; `api key` and bare `key` accepted as limits (documented and pinned by a test) |
| 74 | security (final re-check) | LOW | Over-redaction of keys containing a credential word as a substring (`tokenizer`, `secretary`, `cookie_policy`, `passwordless`) | accepted (documented, pinned) |
| 75 | security (final re-check) | MEDIUM | `secrets=` cost grows with the number of secrets (2000 secrets on 1 MB took 80 s; 3 secrets 0.4 s); the linear scan itself is fast (1 MB under 1 s even for 500k `a=` pairs) | accepted for the intended use (2-3 secrets, log-sized text); documented; a test pins 3 secrets on 1 MB under 2 s |

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
`ruff check .`, `ruff format --check .`, `mypy src` (strict; historical: task 1 gate, now `mypy src tests`), `pytest -q` (21 tests then), `python scripts/check_licenses.py`: all pass locally (Python 3.13 venv). CI gate on the PR runs the same on 3.12.

## Next tasks (separate plan entries, can start in parallel after this merges)
- Tasks 2a `state`, 2b `metrics`, 2c `source` (per-module plans in `specs/plans/`); then 3 `app` + e2e; then 4 tools and deployment; then 5 `generate_config`.
