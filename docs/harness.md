# Harness, agents and deployment

## Agent roster (`.claude/agents/`)

Imported from everything-claude-code, adapted where noted. Rules in `.claude/rules/common` and `.claude/rules/python`; skills `python-patterns`, `python-testing`, `fastapi-patterns` in `.claude/skills/`.

| Agent | Model | Role in this project | Stage |
|---|---|---|---|
| architect | sonnet | Design of module boundaries and `contracts.py`; ADRs for open questions (HmIP client choice) | Design |
| chief-of-staff | haiku | **Adapted:** coordinator of parallel module worktrees; no messaging | Plan/Build |
| implementer | sonnet | Builds one module, tests first (project agent) | Build |
| python-build-resolver | sonnet | **New (not in ECC):** fixes ruff, mypy and pytest-collection failures with minimal diffs | Build |
| code-simplifier | sonnet | Post-implementation clean-up of recent changes | Build |
| python-reviewer | sonnet | PEP 8, idioms, type hints; mandatory per change | Review |
| fastapi-reviewer | sonnet | Async correctness, dependency injection, production readiness for `app/` | Review |
| code-reviewer | sonnet | General quality and maintainability pass | Review |
| security-reviewer | sonnet | Secrets, token handling, SSRF, container hardening | Review |
| performance-optimizer | sonnet | Poll cost, memory, event-loop blocking, scrape latency (`cProfile`, `tracemalloc`) | Test |
| e2e-runner | sonnet | **Adapted:** app + fake upstream + HTTP assertions, not browser | Test |
| verifier | sonnet | Runs the app and checks `/metrics` before "done" (project agent) | Test |
| doc-updater | haiku | Keeps CLAUDE.md, SBOM manifest, harness and spec catalogue in sync after merges (documentation only) | Maintain |
| harness-optimizer | sonnet | Tunes this harness (CLAUDE.md, hooks, agents) from eval results | Maintain |

Suggested flow per module: `architect` → `implementer` → `python-build-resolver` (if needed) → `code-simplifier` → `python-reviewer` + `code-reviewer` + `security-reviewer` → `verifier` / `e2e-runner`. The author never approves its own change.

**Model policy:** Sonnet is the ceiling (no Opus agents; `architect` was downgraded from opus). Haiku for documentation/coordination-only agents (`doc-updater`, `chief-of-staff`). Anything that writes or judges code stays on Sonnet.

## Harness suggestions

- **Hooks** (`.claude/settings.json`, in place): after every `.py` edit run `ruff format` and `ruff check` on the file (fast, file-scoped; exit 2 returns the error to the agent; skipped if ruff is absent). mypy and full tests at commit/PR.
- **To add:** `PreToolUse` hook blocking edits outside the agent's owned module (read the module from an env var set per worktree); block edits to `docs/sbom/sbom.cdx.json` and pinned requirements by hand.
- **Worktrees:** `claude --worktree source`, `--worktree state`, `--worktree metrics`. Start with three sessions.
- **Evals:** `evals/*.json` of 20-50 real tasks with `check.sh` acceptance (e.g. "add metric via YAML only", "battery metric appears for fixture device"), run in CI on any change to CLAUDE.md, rules, agents or hooks. Each incident adds an eval. `harness-optimizer` owns tuning.
- **Maintain:** `bands.yaml` later, mapping poll-error and staleness bands to actions.

## Deployment harness

- **Image:** multi-stage Dockerfile (build wheels in a builder, copy into `python:3.12-slim`), non-root user, single `CMD ["uvicorn", "homematic_exporter.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "9100"]`, `HEALTHCHECK` using Python's `urllib` against `/health` (no curl in slim).
- **Config:** env vars only (`LISTEN_ADDR`, `POLL_INTERVAL`, `STATE_DIR`, `METRICS_CONFIG`, `HMIP_*`). Under systemd/podman pass explicitly (`-e VAR=${VAR}`) and verify with `printenv`.
- **Podman Quadlet** (`deploy/homematic-exporter.container`): single replica, state volume mounted 0700, read-only root fs, `--cap-drop=ALL`, publish `9100` on the internal network only.
- **CI (GitHub Actions):** see intent section "CI/CD and image delivery" (multi-arch arm64+amd64, Docker Hub, PR tags). Summary: `ruff`, `mypy`, `pytest`, `pip-audit`, build image, generate CycloneDX SBOM, sign (cosign) and push; fail on SBOM/`go.mod` drift. Agent evals as a scheduled job.
- **Release:** tag → image + SBOM attached. Production deploy gated by a human approval; the agent that wrote the code cannot approve it.
- **Observability:** Prometheus alerts: stale data (`time() - homematic_last_successful_poll_timestamp_seconds > 300`), `rate(homematic_poll_errors_total[10m]) > 0`, any `homematic_device_low_battery == 1` ("prepare charged accumulators"), `homematic_device_unreachable == 1` for 15m.

## Potential scaffold

```
homematic_exporter/
├── CLAUDE.md
├── REVIEW.md
├── pyproject.toml                 ruff, mypy, pytest config
├── requirements.txt / requirements-dev.txt   pinned
├── Makefile                       test, lint, types, audit, sbom, e2e
├── metrics.yaml                   metric definitions (default config)
├── src/homematic_exporter/
│   ├── contracts.py               Snapshot, Source, StateStore protocols
│   ├── source/        (+CLAUDE.md)
│   ├── state/         (+CLAUDE.md)
│   ├── metrics/       (+CLAUDE.md)
│   └── app/           (+CLAUDE.md)  create_app factory, lifespan
├── tests/{source,state,metrics,app,e2e}/   fixtures per module; e2e marked
├── intent/homematic-exporter.intent.md
├── specs/{README.md,spec.md,plan.md}
├── docs/{harness.md,sbom/{components.md,sbom.cdx.json}}
├── deploy/{Dockerfile,homematic-exporter.container,prometheus-alerts.yml}
├── evals/                         agent evals + check.sh
├── .github/workflows/{ci.yml,agent-evals.yml,release.yml}
└── .claude/{settings.json,hooks/,agents/,rules/{common,python}/}
```

## Risks and decisions for you

1. **Homematic IP client:** spike done, `homematicip` 2.23.1 is the pick; open: GPL-3.0 licence decision and a real-device fixture (see `docs/spikes/`).
2. **e2e-runner and chief-of-staff** are ECC agents built for other jobs; adapted with an appended section rather than rewritten.
3. **python-build-resolver** is a new agent written here, because ECC's `build-error-resolver` is TypeScript-specific and it has no Python build resolver.
4. The ECC agents contain a "Prompt Defense Baseline" and may reference other ECC skills not installed here.
