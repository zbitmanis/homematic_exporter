# Homematic IP heating exporter (Python)

Prometheus exporter: polls Homematic IP, caches values, serves `/metrics`. Read `intent/homematic-exporter.intent.md` first, then `docs/sbom/components.md` for module ownership and `docs/harness.md` for the agent roster. Rules live in `.claude/rules/` (common + python); skills in `.claude/skills/`.

## Commands
(Fill in as the scaffold lands; keep each with healthy output.)
- Install: `pip install -r requirements-dev.txt` (Python 3.12)
- Test: `pytest -q` (expect all passed, no network)
- Lint: `ruff check . && ruff format --check .` (expect no output / "already formatted")
- Types: `mypy src tests` (expect "Success: no issues found")
- Audit: `pip-audit -r requirements.txt` and `python scripts/check_licenses.py` (licence allowlist; expect `homematicip` listed as EXCEPTION)
- E2E: `pytest -m e2e tests/e2e`
- Run: `uvicorn homematic_exporter.app:create_app --factory --port 9100`

## Architecture
- Modules under `src/homematic_exporter/`: `source`, `state`, `metrics`, `app`. Shared contracts: `contracts.py`, `config_models.py`, `redact.py` (scrub). Modules never import each other (`tests/test_import_boundaries.py`).
- Poll loop (asyncio background task) updates metrics; scrapes read cache only. Never call the source from a request handler.
- Mapping is config: a mounted `config.yaml` (default `/etc/homematic-exporter/config/config.yaml`, bundled fallback) holds model names, raw field names, channel types, metric definitions and tuning; adding a metric or numeric field must not need Python changes. Joins, naming, battery history and derived metrics stay in code. Validate with `python -m homematic_exporter.check_config`. See `specs/spec.md` 5.1.
- Config is env vars with defaults; no hardcoded URLs, ports, paths or intervals.
- Lifespan-managed shutdown: the poll task is cancelled and awaited on app shutdown.

## Conventions
- Follow `.claude/rules/python/*` and `.claude/rules/common/*`. Type hints everywhere; `Protocol` for module interfaces.
- Names: `homematic_<thing>_<unit>`, `_total` for counters, base units (celsius, seconds, ratio).
- Labels: `room`, `device_type`, `device` (human-readable name) only. Never SGTIN/serial/timestamp.
- Battery/accumulator status is a first-class metric set (low-battery, unreachable, low-since, last-replaced); do not drop it when trimming scope.
- Every poll updates `homematic_last_successful_poll_timestamp_seconds`, poll duration and `homematic_poll_errors_total`.
- Use a collector callback for scrape-time values that may be absent (e.g. data age: no series before the first success); `Gauge.set_function` only when the value always exists. `yaml.safe_load` only. Use `logging`, not `print`.
- Log upstream error bodies on failure. Never log tokens or PINs.
- State dir 0700, files 0600. Read-only integration: no writes to the heating system.

## Workflow
- One agent = one module = one worktree (`claude --worktree <module>`). Edit only your module's paths.
- Plan first; commit your module plan `specs/plans/<module>.md` before code (the master `specs/plan.md` is the coordinator's). Update your module plan in the same commit if you deviate.
- Changing `contracts.py`, `config_models.py` or `redact.py` (or a module interface) requires a `specs/spec.md` change in that commit, in its own small PR merged before dependent work. Phase-2 agents never edit them (spec 12.1).
- Dependency changes require an SBOM update (`docs/sbom/`), a licence check against the allowlist, and human sign-off. Do not bump versions.
- Licensing: repo is MIT; `homematicip` is GPL-3.0 (accepted exception). Never copy external code/agents/docs without a recorded licence and an entry in `THIRD_PARTY_NOTICES.md`. Do not edit `LICENSE` or `THIRD_PARTY_NOTICES.md` without owner approval. See the intent's Licensing section.
- Bug fix = failing test first, committed before the fix.
- Git: never commit on `main`; no Co-Authored-By footer. Branch as `feat/<name>` or `fix/<name>`; commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:` ...).
- Agents: `python-reviewer` (+ `fastapi-reviewer` for `app/`) and `security-reviewer` on every change; `python-build-resolver` when the gate fails; see `docs/harness.md`.

## Verification
Run tests, lint and types before reporting any task complete, and paste the output. If a test fails, fix the code, not the test.

## Things Claude gets wrong (add to this when a mistake happens twice)
- Putting SGTIN/serial in a label (the friendly `device` name is allowed, the ID is not).
- Calling the source inside the `/metrics` handler.
- Letting an exception in the poll loop end the task; catch, log the body, count it (but let `CancelledError` propagate).
- Blocking the event loop with sync I/O inside async code.
- Assuming Homematic field names without the captured fixture (`tests/source/fixtures/state.scrubbed.json`, git-ignored, local only). Tests must use a small hand-written fixture derived from it, never the full dump.
- Adding debug routes that are on by default.
- Inspecting or resolving a package with an interpreter that differs from `.python-version` (host Python 3.9 once resolved homematicip 1.1.5 instead of 2.x); record Python and resolved version in the spike header.
- Adding a dependency or pasting external code without checking its licence and updating the SBOM / `THIRD_PARTY_NOTICES.md`.
- Flattening `.claude/rules/` when copying; keep `common/` and `python/` directories.
