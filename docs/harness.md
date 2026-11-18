# Harness, agents and deployment

## Agent roster (`.claude/agents/`)

Imported from everything-claude-code (MIT; attribution and licence in `THIRD_PARTY_NOTICES.md`) and rewritten for Python (no npm/Node/React/browser content remains); Sonnet is the ceiling. Rules in `.claude/rules/common` and `.claude/rules/python`; skills `python-patterns`, `python-testing`, `fastapi-patterns` in `.claude/skills/`.

| Agent | Model | Role in this project | Stage |
|---|---|---|---|
| architect | sonnet | Design of module boundaries and the shared contracts (`contracts.py`, `config_models.py`, `redact.py`); ADRs for open questions (HmIP client choice) | Design |
| chief-of-staff | haiku | Rewritten: coordinator of parallel module worktrees; no messaging | Plan/Build |
| implementer | sonnet | Builds one module, tests first (project agent) | Build |
| python-build-resolver | sonnet | **New (not in ECC):** fixes ruff, mypy and pytest-collection failures with minimal diffs | Build |
| code-simplifier | sonnet | Post-implementation clean-up of recent changes | Build |
| python-reviewer | sonnet | PEP 8, idioms, type hints; mandatory per change | Review |
| fastapi-reviewer | sonnet | Async correctness, dependency injection, production readiness for `app/` | Review |
| code-reviewer | sonnet | General quality and maintainability pass | Review |
| security-reviewer | sonnet | Secrets, token handling, SSRF, container hardening | Review |
| performance-optimizer | sonnet | Poll cost, memory, event-loop blocking, scrape latency (`cProfile`, `tracemalloc`) | Test |
| e2e-runner | sonnet | Rewritten: app + fake upstream + HTTP assertions, container smoke test; no browser tooling | Test |
| verifier | sonnet | Runs the app and checks `/metrics` before "done" (project agent) | Test |
| doc-updater | haiku | Keeps CLAUDE.md, SBOM manifest, harness and spec catalogue in sync after merges (documentation only) | Maintain |
| harness-optimizer | sonnet | Tunes this harness (CLAUDE.md, hooks, agents) from eval results | Maintain |

Review phases, statuses and the review log are tracked in `specs/plan.md` (closing review task R1-R10 at the end of every plan, phase reviews P1-P8).

Suggested flow per module: `architect` → `implementer` → `python-build-resolver` (if needed) → `code-simplifier` → `python-reviewer` + `code-reviewer` + `security-reviewer` → `verifier` / `e2e-runner`. The author never approves its own change.

**Model policy:** Sonnet is the ceiling (no Opus agents; `architect` was downgraded from opus). Haiku for documentation/coordination-only agents (`doc-updater`, `chief-of-staff`). Anything that writes or judges code stays on Sonnet.

## Harness suggestions

- **Hooks** (`.claude/settings.json`, in place): after every `.py` edit run `ruff format` and `ruff check` on the file (fast, file-scoped; exit 2 returns the error to the agent; skipped if ruff is absent). mypy and full tests at commit/PR.
- **Built (task 1c):** `.claude/ownership.yaml` (single source of truth), the `ownership` CI check (`scripts/check_ownership.py`, rules and checker taken from the base branch, branch scheme `feat|fix/<name>`), the path-guard `PreToolUse` hook (`.claude/hooks/path_guard.py`: blocks module agents outside their module and worktree, fails closed for them, only warns the coordinator about shared contracts) and `scripts/new_module_worktree.sh`. **Still open:** block hand edits to `docs/sbom/sbom.cdx.json` and `requirements*.txt` for coordinator edits too; make `ownership` a required status check (owner action).
- **Worktrees:** `scripts/new_module_worktree.sh state|metrics|source|app`, one session each (writes the `.hmx-module` marker the hook needs). Start with three sessions.
- **Evals (planned, `evals/` does not exist yet):** `evals/*.json` of 20-50 real tasks with `check.sh` acceptance (e.g. "add metric via YAML only", "battery metric appears for fixture device"), run in CI on any change to CLAUDE.md, rules, agents or hooks. Each incident adds an eval. `harness-optimizer` owns tuning.
- **Maintain:** `bands.yaml` later, mapping poll-error and staleness bands to actions.

## Deployment harness

- **Image:** multi-stage Dockerfile (build wheels in a builder, copy into `python:3.12-slim`), non-root user, single `CMD ["uvicorn", "homematic_exporter.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "9100"]`, `HEALTHCHECK` using Python's `urllib` against `/health` (no curl in slim).
- **Config:** env vars only (`LISTEN_HOST`, `LISTEN_PORT`, `POLL_INTERVAL_SECONDS`, `STATE_DIR`, `CONFIG_FILE`, `APP_VERSION`, `HMIP_*`: see spec section 5). Under systemd/podman pass explicitly (`-e VAR=${VAR}`) and verify with `printenv`.
- **Podman Quadlet** (`deploy/homematic-exporter.container`): single replica, state volume mounted 0700, read-only root fs, `--cap-drop=ALL`, publish `9100` on the internal network only.
- **CI (GitHub Actions):** see intent section "CI/CD and image delivery" (multi-arch arm64+amd64, Docker Hub, PR tags). Summary: `ruff`, `mypy`, `pytest`, `pip-audit`, build image, generate CycloneDX SBOM, push; **planned:** sign (cosign), fail on SBOM/`requirements.txt` drift. Agent evals as a scheduled job.
- **Release:** tag → image + SBOM attached. Production deploy gated by a human approval; the agent that wrote the code cannot approve it.
- **Observability:** Prometheus alerts: stale data (`time() - homematic_last_successful_poll_timestamp_seconds > 300`), `rate(homematic_poll_errors_total[10m]) > 0`, any `homematic_device_low_battery == 1` ("prepare charged accumulators"), `homematic_device_unreachable == 1` for 15m.

## Potential scaffold

```
homematic_exporter/
├── CLAUDE.md
├── REVIEW.md
├── pyproject.toml                 ruff, mypy, pytest config
├── requirements.txt / requirements-dev.txt   pinned
├── Makefile                       (planned) test, lint, types, audit, sbom, e2e
├── config/default-config.yaml     default mapping + metric definitions (bundled; mounted override at /etc/homematic-exporter/config/)
├── src/homematic_exporter/
│   ├── contracts.py               Snapshot, Source, StateStore protocols
│   ├── config_models.py           ExtractConfig, Tuning (shared config models)
│   ├── redact.py                  scrub() (shared credential scrubbing)
│   ├── source/        (+CLAUDE.md)
│   ├── state/         (+CLAUDE.md)
│   ├── metrics/       (+CLAUDE.md)
│   └── app/           (+CLAUDE.md)  create_app factory, lifespan
├── tests/{source,state,metrics,app,e2e}/   fixtures per module; e2e marked
├── intent/homematic-exporter.intent.md
├── specs/{README.md,spec.md,plan.md}
├── docs/{harness.md,sbom/{components.md,sbom.cdx.json}}
├── Dockerfile                     (exists, repo root)
├── deploy/{homematic-exporter.container,prometheus-alerts.yml}   (planned, task 4)
├── evals/                         agent evals + check.sh
├── .github/workflows/{ci.yml,agent-evals.yml,release.yml}
└── .claude/{settings.json,hooks/,agents/,rules/{common,python}/}
```

## Risks and decisions for you

1. **Homematic IP client:** spike done, `homematicip` 2.23.1 is the pick; open: GPL-3.0 licence decision and a real-device fixture (see `docs/spikes/`).
2. **e2e-runner and chief-of-staff** are ECC agents built for other jobs; adapted with an appended section rather than rewritten.
3. **python-build-resolver** is a new agent written here, because ECC's `build-error-resolver` is TypeScript-specific and it has no Python build resolver.
4. The ECC agents contain a "Prompt Defense Baseline" and may reference other ECC skills not installed here.
