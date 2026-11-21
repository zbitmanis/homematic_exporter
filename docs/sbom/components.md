# SBOM: Homematic exporter (Python)

Two parts: (1) a **module manifest** that agents use to divide work, and (2) a **dependency SBOM** for supply-chain tracking.

## 1. Module manifest (ownership and interfaces)

Package root: `src/homematic_exporter/`. One agent owns one module per worktree. Never edit a module you do not own; request the change through the spec.

| Module | Path | Owns | Public interface | Depends on | Proof |
|---|---|---|---|---|---|
| contracts | `contracts.py`, `config_models.py`, `redact.py` | `Snapshot` and entity types, `Source`/`StateStore` protocols, `NameCollisionError`, `ExtractConfig`/`Tuning` config models, `scrub` | the types and `scrub` themselves | pydantic (config models only) | mypy, `tests/test_contracts.py`, `test_config_models.py`, `test_redact.py`, `test_import_boundaries.py`; changes need a spec change and their own PR |
| source | `source/` | Homematic IP cloud client (`CloudSource`, CCU later), local JSON file client (`FileSource`, `SOURCE_KIND=file`), raw-JSON parser, collision and unmapped-model logging (`SnapshotBuilder`, internal) | exports `CloudSource`, `FileSource`, `parse_snapshot`, `parse_with_report`, `ParseReport`; both sources implement `Source.fetch(on_collision) -> Snapshot` (async); `parse_snapshot(raw, now, extract, on_collision)` raises `UpstreamError` unless `raw` has `devices` and `groups` objects; keyword-only `clock` (both sources) and `home_factory` (CloudSource) are test seams | contracts, config_models, redact; `homematicip` 2.23.1 (pinned in `requirements.txt`, imported lazily in `source/cloud.py` only) | `tests/source/` (`test_parser.py`, `test_file_source.py`, `test_cloud.py`) on the shared `tests/fixtures/mini_state.json` and `default_extract`, no network |
| state | `state/` | Battery history on the volume | `FileStateStore` implements `StateStore` (0700/0600), raises `StateDirError`; `BatteryHistory(store, tuning).update(devices, now)` | contracts, config_models | `tests/state/test_store.py`, `tests/state/test_battery.py` (tmp_path, permissions, corrupt files, failed saves) |
| metrics | `metrics/` | `config.yaml` schema and loading (`AppConfig`, `MetricDef`, `Transform`, `ConfigError`), metric definitions to Prometheus objects, derived and meta metrics, the `metrics:` list of `config/default-config.yaml` (14 entity metrics) | exports `load_config`, `parse_config`, `AppConfig`, `ConfigError`, `MetricDef`, `Transform`, `Registry`, `render`; `Registry.build(metric_defs, tuning, version, *, clock)` raises `ConfigError`; `Registry.update/record_success/record_error/exposition`; `record_success` raises `ValueError` outside the timestamp bounds or for a bad duration; `scale` only with transform `none` | contracts, config_models, redact; PyYAML 6.0.3 (`SafeLoader` subclass), pydantic 2.14.3, prometheus_client 0.26.0 (all pinned in `requirements.txt`) | `tests/metrics/` (`test_load_config.py`, `test_schema.py`, `test_registry.py`, `test_default_config.py`, `test_hardening*.py`) with the golden `golden/default_config.prom` from a hand-built `Snapshot` |
| app | `app/` | FastAPI, poll loop, env config, logging filter | `create_app(*, settings=None, config=None, source=None, store=None) -> FastAPI` (env defaults); `/metrics /health /status` | contracts; concrete implementations only in `app/wiring.py` | fake Source, loop-error survival, clean shutdown |

Machine-readable ownership: `.claude/ownership.yaml`, enforced by the `ownership` CI check and the path-guard hook; keep this table and that file in sync. Contract changes (`contracts.py`, `config_models.py`, `redact.py`) need `specs/spec.md` in the same PR.

Dependency direction: `app` wires concrete `source`, `state`, `metrics` and depends only on `contracts` types. Other modules never import each other's concrete classes.

Parallel-safe split: the shared contracts (`contracts.py`, `config_models.py`, `redact.py`) are done and human-reviewed; then source, state and metrics are built simultaneously; app against fakes; e2e last.

## 2. Dependency SBOM

Format: CycloneDX JSON, generated in CI, committed per release as `docs/sbom/sbom.cdx.json`. Never hand-edit it.

```bash
pip install cyclonedx-bom pip-audit
cyclonedx-py requirements requirements.txt -o docs/sbom/sbom.cdx.json
pip-audit -r requirements.txt
```

Resolved and pinned 2026-11-18 in `requirements.txt` / `requirements-dev.txt` (resolved on Python 3.13; target runtime is Python 3.12, verify in CI). `pip-audit`: no known vulnerabilities. Generated SBOM: `docs/sbom/sbom.cdx.json` (CycloneDX 1.6, runtime deps only).

| Component | Pinned | Purpose | Module | Licence | Note |
|---|---|---|---|---|---|
| fastapi | 0.165.0 | web app | app | MIT | pulls starlette, pydantic |
| uvicorn | 0.54.0 | ASGI server | app | BSD-3 | single `CMD` |
| prometheus_client | 0.26.0 | metric objects, exposition | metrics, app | Apache-2.0 / BSD-2 | |
| pydantic | see `requirements.txt` | config models and validation (imported directly by `config_models.py`) | contracts, metrics | MIT | direct import; pinned directly in `requirements.txt` (also pulled in by fastapi) |
| PyYAML | 6.0.3 | metric config | metrics | MIT | `SafeLoader` subclass only (strict loader in `metrics/config.py`), never `yaml.load` |
| homematicip | 2.23.1 | HmIP cloud API client | source | **GPL-3.0-or-later** | spike: `docs/spikes/homematicip-spike.md`; needs Python >=3.12; pulls aiohttp, httpx2, opentelemetry-api |
| httpx, pytest, pytest-asyncio | 0.28.1 / 9.2.0 / 1.5.0 | tests | all | BSD / MIT | dev only |
| ruff, mypy, types-PyYAML | 0.17.5 / 2.4.1 / see file | lint, format, types | all | MIT | dev only |
| pip-audit, pip-licenses, cyclonedx-bom | see file | supply-chain tooling | CI | Apache-2.0 / MIT | dev only |

Runtime dependencies (29 pinned packages in total, direct and transitive) are listed in the generated SBOM. Other licences seen: PSF (typing_extensions, aiohappyeyeballs), MPL-2.0 (certifi), Apache-2.0 (aiohttp, multidict, yarl, frozenlist, propcache, opentelemetry-api).

### Licence decision (updated 2026-11-18)
`homematicip` is GPL-3.0-or-later, outside the allowlist. **Decision (owner): this repository is licensed MIT, and the GPL dependency is accepted.** Consequences:
- Our own code is MIT (`LICENSE`). MIT is GPL-compatible, so combining is allowed.
- The Docker Hub repo is **public**, so the image **is distributed**; the combined image is then distributed under GPL-3.0-or-later terms for the whole work (see `THIRD_PARTY_NOTICES.md`). The earlier condition "image and source stay private" no longer applies.
- CI licence check treats `homematicip` as an explicit, documented exception.
- If the GPL terms become unacceptable, the alternative is replacing `homematicip` with an own `httpx` client (clean-room, no GPL source reuse).

#### Image distribution checklist (for the Dockerfile and release workflow)
- [x] Copy `LICENSE`, `THIRD_PARTY_NOTICES.md` and the GPL-3.0 text into the image: `/licenses/` in the `Dockerfile` (GPL text in `LICENSES/GPL-3.0-or-later.txt`); image build not yet run
- [x] Label the image: `org.opencontainers.image.licenses="MIT AND GPL-3.0-or-later"`, `source`, `revision` (Dockerfile `LABEL` and workflow `labels:`)
- [ ] State in the Docker Hub description that the image bundles `homematicip` (GPL-3.0-or-later) with a source link: text ready in `docs/dockerhub-description.md`, **paste it manually** (automation is a follow-up)
- [ ] Attach the CycloneDX SBOM to releases (already planned)
- [x] Re-check the licence list on every dependency change: `python scripts/check_licenses.py` runs in the CI gate (allowlist, `homematicip` exception)

Runtime image: multi-stage, slim Python base (record the base image digest in the SBOM at build).

Rules:
- Adding or bumping a dependency requires an SBOM update in the same commit and human sign-off. Agents must not bump versions on their own.
- CI fails if `requirements.txt` and the SBOM disagree, `pip-audit` reports a vulnerability, or a licence is outside the allowlist (MIT, BSD, Apache-2.0, PSF, MPL-2.0, ISC) other than the documented `homematicip` exception.

## 3. Dependency inspection policy (lesson learned)

**Incident, 2026-11-18:** the first `homematicip` spike used a venv on the host's default Python 3.9, which resolved the old 1.1.5 line. The target is Python 3.12 and the current line is 2.23.1 (needs >=3.12). It was noticed only when pins were resolved on 3.13. Root cause: the inspection environment did not match the target runtime, and nothing recorded which version and Python were inspected. The findings were redone on 2.23.1.

Rules (in force now):
- Inspect and resolve only with the interpreter in `.python-version` (currently 3.12). Never use the host default Python.
- Every spike doc starts with the header in `docs/spikes/_TEMPLATE.md` (package, resolved version, Python, date, sources, live_verified). `python` must equal `.python-version`.
- Version policy: latest stable that installs on the target Python; fall back to N-1 minor if the latest is under 14 days old or has open regressions; treat a package as maintained only with a release in the last 12 months. Exact `==` pins in generated files, major-version bounds in `.in` files. Bumps need an SBOM update and human sign-off.

Proposed, not yet built (architect recommendation, awaiting your go):
1. `requires-python = ">=3.12,<3.13"` in `pyproject.toml`; Dockerfile `ARG PYTHON_VERSION=3.12` checked against `.python-version`.
2. `requirements.in` / `requirements-dev.in` as the source of pins; `make lock` using `uv pip compile --python-version $(cat .python-version)`; `make inspect PKG=...` using `uv venv --python`. (`uv` is not installed here; pip-only fallback: `pip download PKG --python-version 3.12 --only-binary=:all: --no-deps`.)
3. CI `lock-drift` job: run `make lock`, `git diff --exit-code requirements*.txt`, then `pip-audit`, licence check (exception: homematicip) and SBOM drift. Run on PRs touching requirements plus a weekly schedule.
4. `scripts/check_spike_headers.py` plus an eval `evals/spike-wrong-python.json` so a spike with the wrong Python fails.
