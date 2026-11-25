# Homematic IP heating exporter (Python)

Prometheus exporter: polls Homematic IP, caches values, serves `/metrics`. Read `intent/homematic-exporter.intent.md` first, then `docs/sbom/components.md` for module ownership and `docs/harness.md` for the agent roster. Rules live in `.claude/rules/` (common + python); skills in `.claude/skills/`.

## Commands
(Fill in as the scaffold lands; keep each with healthy output.)
- Install: `pip install -r requirements-dev.txt` (Python 3.12)
- Test: `pytest -q` (expect all passed, no network)
- Lint: `ruff check . && ruff format --check .` (expect no output / "already formatted")
- Types: `mypy src tests` (expect "Success: no issues found")
- Ownership: `python scripts/check_ownership.py --base origin/main --branch $(git branch --show-current)` (expect `ownership ok`)
- Audit: `pip-audit -r requirements.txt` and `python scripts/check_licenses.py` (licence allowlist; expect `homematicip` listed as EXCEPTION)
- E2E: `pytest -m e2e tests/e2e` (after task 3; until then it exits with code 5 = no tests collected, as `tests/e2e` has no tests yet)
- Run: `uvicorn homematic_exporter.app:create_app --factory --port 9100` (after task 3; `create_app` does not exist yet)

## Architecture
- Modules under `src/homematic_exporter/`: `source`, `state`, `metrics`, `app`. Shared contracts: `contracts.py`, `config_models.py`, `redact.py` (scrub). Modules never import each other (`tests/test_import_boundaries.py`).
- Poll loop (asyncio background task) updates metrics; scrapes read cache only. Never call the source from a request handler.
- Mapping is config: a mounted `config.yaml` (default `/etc/homematic-exporter/config/config.yaml`, bundled fallback; the four-step chain is in `src/homematic_exporter/metrics/CLAUDE.md`) holds model names, raw field names, channel types, metric definitions and tuning; adding a metric or numeric field must not need Python changes. Joins, naming, battery history and derived metrics stay in code. Validate with `python -m homematic_exporter.check_config` (planned, task 4). See `specs/spec.md` 5.1.
- Config is env vars with defaults; no hardcoded URLs, ports, paths or intervals.
- Lifespan-managed shutdown: the poll task is cancelled and awaited on app shutdown.

## Conventions
- Follow `.claude/rules/python/*` and `.claude/rules/common/*`. Type hints everywhere; `Protocol` for module interfaces.
- Names: `homematic_<thing>_<unit>`, `_total` for counters, base units (celsius, seconds, ratio).
- Labels: `room`, `device_type`, `device` (human-readable name) only. Never SGTIN/serial/timestamp.
- Battery/accumulator status is a first-class metric set (low-battery, unreachable, low-since, last-replaced); do not drop it when trimming scope.
- Each successful poll sets `homematic_last_successful_poll_timestamp_seconds` and `homematic_poll_duration_seconds`; each failed poll increments `homematic_poll_errors_total`. The first two have no series until the first success.
- Use a collector callback for scrape-time values that may be absent (e.g. data age: no series before the first success); `Gauge.set_function` only when the value always exists. SafeLoader (strict subclass in metrics) only, never `yaml.load`. Use `logging`, not `print`.
- Log upstream error bodies on failure. Never log tokens or PINs.
- State dir 0700, files 0600. Read-only integration: no writes to the heating system.

## Workflow
- One agent = one module = one worktree. Edit only your module's paths (`.claude/ownership.yaml`).
- Start module work **only** with `scripts/new_module_worktree.sh <module> [branch]` (worktree, `feat/<module>` branch, `.hmx-module` marker). `claude --worktree` writes no marker, so the hook would not guard it. The path-guard hook blocks edits outside your module and outside your worktree (it cannot see shell edits or `rm .hmx-module`); the `ownership` CI check is the real enforcement (run from the base branch's copy). Branches must be `feat/<name>` or `fix/<name>`; names that merely start like a module (`feat/state2`) fail. Until the guard is merged to `main`, a worktree from `main` has no marker and no hook.
- Plan first; commit your module plan `specs/plans/<module>.md` before code (the master `specs/plan.md` is the coordinator's). Update your module plan in the same commit if you deviate.
- Changing `contracts.py`, `config_models.py` or `redact.py` (or a module interface) requires a `specs/spec.md` change in that commit, in its own small PR merged before dependent work. Phase-2 agents never edit them (spec 12.1).
- Dependency changes require an SBOM update (`docs/sbom/`), a licence check against the allowlist, and human sign-off. Do not bump versions.
- Licensing: repo is MIT; `homematicip` is GPL-3.0 (accepted exception). Never copy external code/agents/docs without a recorded licence and an entry in `THIRD_PARTY_NOTICES.md`. Do not edit `LICENSE` or `THIRD_PARTY_NOTICES.md` without owner approval. See the intent's Licensing section.
- Bug fix = failing test first, committed before the fix.
- Every plan ends with the **closing review task** (`specs/plan.md` section A, steps R1-R10: gate (R1), python/fastapi, code, security, architecture, simplify, performance, verify/e2e, docs, owner). Do not open the PR until it is complete; paste each verdict into the PR description.
- Git: never commit on `main`; no Co-Authored-By footer. Branch as `feat/<name>` or `fix/<name>`; commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:` ...).
- Agents: `python-reviewer` (+ `fastapi-reviewer` for `app/`) and `security-reviewer` on every change; `python-build-resolver` when the gate fails; see `docs/harness.md`.

## Verification
Run tests, lint and types before reporting any task complete, and paste the output. If a test fails, fix the code, not the test.

## Things Claude gets wrong (add to this when a mistake happens twice)
- Putting SGTIN/serial in a label (the friendly `device` name is allowed, the ID is not).
- Calling the source inside the `/metrics` handler.
- Letting an exception in the poll loop end the task; catch, log the body, count it (but let `CancelledError` propagate).
- Blocking the event loop with sync I/O inside async code.
- Assuming Homematic field names without the captured fixture (`tests/source/fixtures/state.scrubbed.json`, git-ignored, local only). Tests use the shared hand-written fixture `tests/fixtures/mini_state.json`, never the full dump.
- Adding debug routes that are on by default.
- Inspecting or resolving a package with an interpreter that differs from `.python-version` (host Python 3.9 once resolved homematicip 1.1.5 instead of 2.x); record Python and resolved version in the spike header.
- Adding a dependency or pasting external code without checking its licence and updating the SBOM / `THIRD_PARTY_NOTICES.md`.
- Flattening `.claude/rules/` when copying; keep `common/` and `python/` directories.
