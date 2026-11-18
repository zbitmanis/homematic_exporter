# Intent: Homematic IP heating Prometheus exporter

- **Author:** andris
- **Status:** accepted 2026-11-18 (owner); `specs/spec.md` drafted (review pending)
- **Stage:** Plan (AI-native SDLC)

## Problem

The home heating system runs on Homematic IP (thermostats, wall thermostats, heating groups, boiler/actuator state). There is no way to see history, compare rooms, or alert on faults (stale sensors, low battery, valve stuck open, room not reaching setpoint) in the existing Prometheus/Grafana stack. A sibling exporter for a Viessmann gas boiler already exists; this one should follow the same operating pattern so both are run the same way.

## Proposed outcome

A small container service that polls Homematic IP, caches the results, and exposes them as Prometheus metrics on `/metrics`. Adding a metric needs a YAML change, not a code change. Success looks like:

1. Prometheus scrapes `/metrics` and per-room temperature, setpoint, valve position, humidity and battery state appear within one poll interval of startup.
2. An alert on `time() - homematic_last_successful_poll_timestamp_seconds > 300` fires when the exporter runs but data is stale.
3. A new metric can be added by editing the mounted `config.yaml` only (mapping is configuration, structure is code; see `specs/spec.md` 5.1).
4. The service survives restarts without re-pairing (the token is supplied as a Podman secret/env; nothing to re-pair).
5. A push to GitHub produces a tested, multi-arch container image on Docker Hub without manual steps; pull requests get automatically tagged builds.
6. **Several coding agents can build it in parallel** without editing each other's files (see "Harness goals").

## Installed devices (scope for v1)

Newly added Homematic IP set:
- Floor heating controller driving **12 valve outputs** (one per zone).
- Wall thermostats with humidity sensors.
- Radiator thermostats.
- Door sensor.
- Most battery devices run on **rechargeable accumulators**, not primary cells.

**Battery readiness is a first-class goal.** The operator wants to know which devices need their accumulators swapped for a charged set, early enough to prepare the spare set. Required signals:
1. Per-device low-battery state (`lowBat`), identifiable by human-readable name.
2. Per-device unreachable state (a dead accumulator often shows up as unreachable first).
3. Battery level or voltage, only if the device/API actually exposes it (open question 6).
4. How long a device has been in low-battery state (needs state across restarts: see `state/`).
5. A "last replaced" signal: detect low-battery true→false and record the time, so accumulator runtime between swaps is visible.

**Decided signals (starting point):** `lowBat`, `unreach`, `rssiDeviceValue` (radio quality) and `deviceUndervoltage`, exposed per device (label `device`), plus low-since and last-replaced derived in `state/`.

Alert examples: any device low-battery > 0 → "prepare charged set"; device unreachable > 15 min.

## Config generator (added 2026-11-18)

Mapping is configuration, not code (see `specs/spec.md` 5.1). To avoid hand-writing it, and to cope with new Homematic IP devices, the project includes a **script that generates a draft `config.yaml` from the state the API returns** (the JSON that `scripts/fixture/dump_state.py` writes as `state.scrubbed.json`, or a fresh download).

Requirements:
1. **Input:** a Homematic IP state JSON file (offline; no credentials needed). Optionally the existing config, to show what is new.
2. **Output:** a draft `config.yaml` with `extract.device_models` for every observed `modelType` (suggested short names), `extract.valves`/`contacts` rules for observed channel types, and `metrics` for the fields found per scope; plus comments listing fields that exist in the data but were not mapped, so new numeric fields can be added as `extras` quickly.
3. **Deterministic and reviewable:** same input gives the same output; every generated entry is marked as a suggestion; the owner reviews and edits before use.
4. **Safe to commit:** the output contains no SGTINs, serials, ids, tokens, PINs, room names or device names, only model types, channel types and raw field names, so a config file may live in git.
5. **Self-checking:** the output passes `check_config` (spec R20) against the same input.

Non-goals: applying the config automatically, calling the API itself (the capture tool does that), guessing semantics beyond field names and types.
Anti-goal: a generator whose output leaks identifying data from the input.

## Affected users and systems

- Home operator (andris): Grafana dashboards and alerts.
- Prometheus scraping on the internal network only.
- Upstream: Homematic IP cloud API via the access point (first source). A local CCU / RaspberryMatic client is a planned second source behind the same interface.
- Sibling project: the Viessmann exporter (pattern donor; no runtime coupling).

## Constraints

- Python 3.12, FastAPI + uvicorn, `prometheus_client`, PyYAML.
- Scrapes read cached values and never hit the source directly.
- Poll errors are caught inside the loop; one failed poll must not kill the service.
- All URLs, paths, ports and intervals are env vars with sane defaults (image stays generic).
- State (battery history) lives on a mounted volume with restricted permissions (dir 0700, files 0600). The auth token comes from a Podman secret/env, not the volume.
- Metric names follow `homematic_<thing>_<unit>`, `_total` for counters, base units (celsius, ratio, seconds).
- Label cardinality is small and bounded: `room`, `device_type`, and `device` (the human-readable device name, ~30 values, needed for "which accumulator do I swap"). Never SGTIN, serials or timestamps as labels.
- Floor heating zones are labelled by `room`/zone name, not by output index alone.
- Meta-metrics are mandatory: last successful poll timestamp, poll duration, poll error count.
- Single replica. The poll loop is not safe to run twice.
- Multi-stage slim image (non-root), one `CMD` starting uvicorn. `/health` for the orchestrator. Debug routes are off by default.
- Log the upstream error body on poll failure, not only the status code.
- Dependencies and licences are tracked in the SBOM (`docs/sbom/`); licensing rules are in the Licensing section below.

## CI/CD and image delivery (added 2026-11-18)

End-to-end pipeline on **GitHub Actions**, image storage on **Docker Hub**.

Requirements:
1. **Multi-arch image:** `linux/arm64` (primary) and `linux/amd64`, published as one manifest list under each tag. Built with QEMU emulation first (decided, Q10); native arm64 runners are a later optimisation.
2. **Runs under Podman** (rootless, primary deployment). Image is OCI-compatible, non-root, read-only-root-fs friendly, and does not depend on Docker-only features. Health is also defined in the Podman Quadlet unit (`HealthCmd`), because Dockerfile `HEALTHCHECK` is ignored for OCI-format builds.
3. **Pipeline stages:** lint, types, tests, e2e (fake upstream), `pip-audit`, licence check, SBOM generation, image build, image scan, push, with the SBOM attached to the image/release.
4. **Automated tagging for pull requests, including a brief summary.** Image tags are generated from commit history: `v<next-version>-pr.<n>.<sha7>` plus `pr-<n>` (open question 8, decided).
5. **Main and releases:** merges to `main` publish `edge` and `sha-<short>`; a version tag `vX.Y.Z` publishes `X.Y.Z`, `X.Y` and `latest`.
6. Docker Hub credentials are repository secrets (access token, not password); never exposed to builds triggered from forks.
7. PR images are cleaned up when the PR closes (or expire via retention).

### Reference pipeline (from `zbitmanis/viessmann_exporter` `release.yml`, read 2026-11-18)
Owner wants a similar pipeline for most of their projects, so this one should be built as a **reusable pattern**, not a one-off. What the reference does:
- Trigger: push to `main` (also `master`, `next`, `beta`, `alpha`). Merging a pull request is the release event.
- `release` job: `semantic-release` (pinned, Renovate-updated) derives the version from Conventional Commits, publishes the GitHub release and writes `.VERSION`; the job outputs `version`, empty when nothing is released.
- `build` job runs only if a version was released: Docker Hub login (`vars.DOCKERHUB_USERNAME`, `secrets.DOCKERHUB_TOKEN`), QEMU, `docker/build-push-action` for `linux/amd64,linux/arm64`, image name from `vars.DOCKERHUB_REGISTRY`.
- Tags pushed: `<version>`, `<version>-amd64`, `<version>-arm64`, `latest`.
- Job-level `permissions`, with checkout and setup-node pinned by commit SHA.

Fit with this project: the Conventional Commit and `feat|fix/` branch rules already match semantic-release; PR titles must also be Conventional Commits (squash merge) so they produce the version.

Gaps to close for this project (proposals, not yet agreed): no test/lint/audit gate before release; no pull-request workflow, so no PR tags (Q8); `-amd64`/`-arm64` tags point at the same multi-arch manifest and are misleading; Docker actions are tag-pinned, not SHA-pinned; QEMU arm64 builds are slow (Q10); no SBOM or provenance attestation; a dead `VERSION=$(cat .VERSION)` line in the release step. The `.releaserc` that writes `.VERSION` has not been read yet.

Non-goals: Kubernetes manifests, multiple registries in v1.

## Licensing (added 2026-11-18)

Goal: never ship something we are not allowed to ship, and never be surprised by a licence at release time.

Decisions in force:
1. **This repository is MIT** (`LICENSE`, copyright holder Andris Zbitkovskis).
2. **`homematicip` is GPL-3.0-or-later** and is accepted. The Docker Hub repo is public, so the published image **is distributed**, and the combined image is under GPL terms for that component. MIT code may be combined with it; the image must carry the GPL notice and a source pointer.
3. **Copied third-party material** (ECC agents, rules, skills under `.claude/`) is MIT-licensed and attributed in `THIRD_PARTY_NOTICES.md`. Anything else copied into the repo needs the same treatment before it is committed.
4. **Dependency licence allowlist:** MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0. Anything else (GPL, LGPL, AGPL, SSPL, unknown, "non-commercial") needs a recorded owner decision in `docs/sbom/components.md`; `homematicip` is the one documented exception.

Rules (enforced by review and CI, see `docs/sbom/components.md`):
- **Before adding or bumping a dependency:** check its licence (PyPI metadata, `pip-licenses`) and record it in the SBOM in the same commit. Copyleft licences stop the change until the owner decides.
- **Before copying code, prompts, agents or docs from elsewhere:** confirm the licence permits it, keep the notice, add it to `THIRD_PARTY_NOTICES.md`.
- **Before any image publish path changes:** the image ships `LICENSE`, `THIRD_PARTY_NOTICES.md` and the GPL text, carries the OCI licence labels, and the Docker Hub description names the bundled GPL library with a source link (checklist in the SBOM doc).
- **Fixtures and docs:** captured device data stays scrubbed and git-ignored; no third-party text pasted into docs without attribution.
- **AI agents:** an agent must not add a dependency, copy external code, or change `LICENSE`/`THIRD_PARTY_NOTICES.md` without owner approval.

Non-goals: dual licensing, a contributor licence agreement, legal review (revisit if the project is published widely or used commercially).

Anti-goal: a release that includes a dependency or copied file with an unrecorded or incompatible licence.

## Non-goals

- Controlling the heating (no setpoint writes, no mode changes). Read-only.
- Running multiple exporter instances or replicas against several access points (out of scope for v1).
- Historical storage or dashboards (Prometheus/Grafana own that).
- Event-driven push of every websocket event as separate metrics.

## Anti-goals (failure even if it technically works)

- A scrape that triggers an upstream call.
- High-cardinality labels or per-device-ID series that churn.
- Auth token or PIN appearing in logs, metrics, `/status` or the image.
- An agent editing outside its owned module, or changing a module interface without a spec update.
- Tests weakened or deleted to make a task pass.

## Harness goals

- Work is split into four modules with declared interfaces and owned paths (`docs/sbom/components.md`).
- Each agent works in its own git worktree on one module.
- Interfaces are the only coordination point; changing one requires a `spec.md` edit in the same commit.
- Each stage commits one artifact (`intent.md` → `spec.md` → `plan.md` → PR).

## Open questions

1. ~~Which Homematic IP library?~~ **Resolved by spike** (`docs/spikes/homematicip-spike.md`): `homematicip` 2.23.1, async, Python >=3.12. Residual: GPL-3.0 licence decision, and confirmation against a real fixture.
2. ~~Field mapping~~ **Answered by the fixture (2026-11-18):** 12 `HEATING` groups = 12 rooms (group label = room). Per room: `actualTemperature`, `setPointTemperature`, `humidity`, `controlMode`, `lowBat`, `unreach`. Room-level `valvePosition` is empty; per-valve positions come from the 11 used `FLOOR_TERMINAL_BLOCK_MECHANIC_CHANNEL`s of the HmIP-FALMOT-C12 (value 0.0-1.0, each channel maps to a room via its `groups`) and from `HmIP-eTRV-B-2` radiator thermostats (`valvePosition`, `valveActualTemperature`). Every device carries `lowBat`, `unreach`, `rssiDeviceValue`, `deviceUndervoltage`.
3. ~~Poll vs websocket~~ **Decided (owner, 2026-11-18): periodic poll**, default 60 s (`POLL_INTERVAL_SECONDS`, changed from 30 s in the spec review, C8). Websocket is a possible later enhancement.
4. ~~Pairing flow~~ **Decided (owner, 2026-11-18): option A.** v1 has no pairing code. The token is generated once with the library's `hmip_generate_auth_token` and supplied to the container as a Podman secret / env (`HMIP_ACCESS_POINT`, `HMIP_AUTH_TOKEN`). A built-in `pair` command is a possible later addition.
5. ~~Boiler state~~ **Answered: not available (derived proxy accepted by owner).** `HEATING_COOLING_DEMAND_BOILER` and `..._PUMP` groups exist but `on` and `heatDemand` are `None`; the circulation-pump switch (HmIP-FSM) also reports `on = None`. Proposal: export a derived `homematic_heat_demand` (any valve position > 0) and `homematic_valves_open` count instead, and revisit if the FSM starts reporting `on`.
6. ~~Battery level?~~ **Answered by spike:** the library exposes only `lowBat`, `unreach`, `rssiDeviceValue` and `deviceUndervoltage` (booleans/RSSI), no voltage or percentage. Low-since and last-replaced tracking is therefore the primary signal.
7. ~~Device naming~~ **Answered by the fixture; label rule accepted by owner: names are NOT unique** (default labels repeat: 5x Wall Thermostat, 4x Radiator Thermostat, 4x Temperature and Humidity Sensor, ...). Rule (proposal): `device` label = `<room> <model-short>` (unique for all 12 rooms in the fixture, no collisions); FALMOT valve channels are labelled by the room they serve; the access point and circulation pump get room `system`. Startup fails loudly on a collision. Renaming devices in the app is optional, not required.
8. ~~PR tag scheme~~ **Decided (owner, 2026-11-18):** no title slug. PR images get a semver tag derived from commit history, `v<next-version>-pr.<n>.<sha7>`, plus the alias `pr-<n>`; same-repo PRs only; image tags only (no git tags); cleaned up on PR close. See `docs/ci/README.md`.
9. **Docker Hub (partly decided 2026-11-18):** image `zbitmanis/homematic-exporter` (namespace `zbitmanis`, repo `homematic-exporter`). Set as GitHub Actions variables `DOCKERHUB_USERNAME=zbitmanis`, `DOCKERHUB_REGISTRY=homematic-exporter` and secret `DOCKERHUB_TOKEN` (owner adds them in the repo). Fork PRs: built, never pushed. Docker Hub repo is **public**. Central repo `zbitmanis/ci-workflows` exists but is empty: v1 uses **local workflows in this repo**, migration to the central repo is a follow-up task (`docs/ci/README.md`).
10. ~~Arm runners~~ **Decided (owner, 2026-11-18): QEMU emulation first**, as in the reference pipeline; revisit native arm runners if build time becomes a problem.


**Update 2026-11-18 (CI/CD design):** the pipeline is designed as a **central reusable workflow pair**, built locally first (`release.yml`, `pr-image.yml`) shared across projects, with thin callers here. Design, drafts and risks: `docs/ci/README.md`. Proposed answers to Q8-Q10 live there (Docker Hub variable names as in the reference repo; QEMU for arm64 first, native arm later). Still need the owner's confirmation.
11. ~~Licensing follow-ups~~ **Done (owner said all yes, 2026-11-18):** copyright holder is Andris Zbitkovskis; `pyproject.toml` has `license = "MIT"` and `license-files`; the licence allowlist check (`scripts/check_licenses.py`) is in the CI gate; the Dockerfile ships `/licenses/` and the OCI licence labels, and the release/PR workflows set labels. Still manual: paste `docs/dockerhub-description.md` into Docker Hub; the image has not been built yet.
