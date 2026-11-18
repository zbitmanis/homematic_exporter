# CI/CD design: local workflows now, central reusable pair as follow-up

**Decision (2026-11-18):** `zbitmanis/ci-workflows` exists but is empty. This repo runs **self-contained local workflows** (`.github/workflows/ci.yml`, `release.yml`) that read `vars.DOCKERHUB_*` directly. Extracting them into the central repo is a **follow-up task** (see the end of this file). The drafts in `docs/ci/central/` are the extraction target and are kept in sync until then.

Status: **draft, untested** (no GitHub repo or Docker Hub access yet). `actionlint` was not available; the YAML parses, nothing has run.
Reference: `zbitmanis/viessmann_exporter` `release.yml` + `package.json` (read 2026-11-18). Release config lives in its `package.json` (`release` key); there is no `.releaserc`, no Renovate config in the repo, Dockerfile is a two-stage alpine build.

## Shape
```
zbitmanis/ci-workflows            (placeholder name; central, versioned with tags v1, v1.x)
└── .github/workflows/
    ├── release.yml               semantic-release -> version -> multi-arch build -> push (+SBOM, provenance)
    └── pr-image.yml              PR: build and push v<next>-pr.<n>.<sha7> and pr-<n>; closed: delete them
<each project>/.github/workflows/
    ├── ci.yml                    project gate job(s) -> calls pr-image.yml
    └── release.yml               push to main -> calls release.yml
```
Drafts live in `docs/ci/central/` here until the central repo exists; callers are in `.github/workflows/`.

**Boundary:** the central workflows know nothing about the language. Lint/test/audit stay in each project's own `gate` job; the image job `needs` it. A Python, Go or Node project differs only in its gate.

## Contract (inputs and what the project must provide)
| Item | Where | Notes |
|---|---|---|
| `dockerhub-username`, `image` | inputs (from repo `vars.DOCKERHUB_USERNAME`, `vars.DOCKERHUB_REGISTRY`, same names as the reference) | Image is `<username>/<image>` |
| `DOCKERHUB_TOKEN` | secret | Docker Hub access token; PR cleanup needs **Read, Write, Delete** scope |
| `platforms` | input, default `linux/amd64,linux/arm64` | |
| `context`, `dockerfile` | inputs | defaults `.` and `Dockerfile` |
| `semantic-release-version` | input, default `25.0.1` | used only when the project has no `package.json` |
| Conventional Commits | project rule | PR title must be a Conventional Commit (squash merge), it becomes the release commit |

## Tags
- **Release** (merge to `main` with a `feat`/`fix`/breaking commit): `X.Y.Z`, `X.Y`, `latest` (no `v` prefix, as in the reference; git tags and the PR tags use `v`. Open: add `v` here too?). Pre-releases (`X.Y.Z-beta.1`) get only the exact tag. The reference's `-amd64`/`-arm64` tags are dropped: they pointed at the same multi-arch manifest.
- **Pull request** (same repo only): `v<next-version>-pr.<n>.<sha7>` (e.g. `v1.4.0-pr.42.a1b2c3d`) and the alias `pr-<n>` (always the latest build of that PR). The next version is derived from Conventional Commit history since the last stable `v*` tag, in plain shell (no Node): breaking -> major, `feat` -> minor, `fix`/`perf` -> patch, otherwise the current version; no tag yet -> `1.0.0` on a releasable commit (semantic-release's start), else `0.0.0`. Tested on a temp git repo (8 cases). **Image tags only: no git tags are created for PRs**, because extra tags would confuse `semantic-release`'s last-release detection. No title slug (owner decision).
- **Fork PRs:** built but never pushed, no secrets.
- **PR close:** `pr-<n>` and every `...-pr.<n>.*` tag are deleted via the Docker Hub API.
- No release is produced when no commit since the last release is `feat`/`fix`/breaking (semantic-release behaviour); `docs:`/`chore:` merges publish nothing.

## Changes from the reference (and why)
| Reference | Draft | Why |
|---|---|---|
| Release on any push to `main` | Same, but project gate runs on the PR first | A failing PR cannot merge once the gate is a required check |
| Needs `package.json` in every repo | Generates a default one in the runner workspace if absent; uses the project's if present | Python/Go repos stay free of Node files |
| QEMU arm64 | QEMU (same); native arm runner is a later optimisation | Q10 decided |
| `-amd64`/`-arm64` tags | removed | misleading |
| Tag-pinned Docker actions | version tags with `TODO pin by SHA` | SHAs could not be looked up offline; add with `pinact`/Renovate |
| none | `sbom: true`, `provenance: true`, gha cache | supply chain; verify Podman handles the attestation manifests (they show as `unknown/unknown`) |
| `npm audit signatures` | dropped | re-add if wanted |
| dead `VERSION=$(cat .VERSION)` | removed | had no effect |

## This project
Image: `zbitmanis/homematic-exporter`. Repo variables `DOCKERHUB_USERNAME=zbitmanis`, `DOCKERHUB_REGISTRY=homematic-exporter`; secret `DOCKERHUB_TOKEN`. (`DOCKERHUB_USERNAME` is used both as the login user and the image namespace; if your Docker Hub login differs from the namespace, tell me and I will split it into two variables.)

## One-time setup per project
1. Repo variables `DOCKERHUB_USERNAME`, `DOCKERHUB_REGISTRY`; secret `DOCKERHUB_TOKEN`.
2. Branch protection on `main`: PR required, `gate` required, squash merge only (so the PR title is the commit).
3. Optional: a "semantic PR title" check so a bad title fails early (not drafted yet).
4. Allow GitHub Actions to create releases (`contents: write` is requested per job).

## Not verified / risks
- Nothing has run. First test: a throwaway repo with a trivial Dockerfile.
- Reusable-workflow `permissions` can only narrow what the caller grants; the caller files grant `contents/issues/pull-requests: write` on the release job.
- `semantic-release` default config assumes branch `main` and no existing `package.json` conflicts.
- Docker Hub login endpoint and tag-delete API for the cleanup job are unverified against a real token.
- The local workflows need a `Dockerfile` and application code to do anything useful: the image build fails until a `Dockerfile` exists (mypy and pytest steps are skipped while `src/`/`tests/` have no Python files). Add the Dockerfile before enabling branch protection on the `gate`/`build` checks.
- Docker Hub repo is **public**, so pushed images (including `pr-*` tags) are world-readable; do not put anything sensitive in the image.

## Follow-up task: migrate to the central repo
1. Prove the local workflows on this repo (real PR, real merge, real Docker Hub push).
2. Commit the drafts from `docs/ci/central/.github/workflows/` (re-synced with the proven local files) to `zbitmanis/ci-workflows` on a `feat/` branch, tag `v1`.
3. Replace the local `ci.yml` image job and `release.yml` with thin callers (`uses: zbitmanis/ci-workflows/.github/workflows/<file>@v1`, inputs from `vars.DOCKERHUB_*`).
4. Pin actions by SHA centrally (Renovate/`pinact`); add an optional semantic-PR-title check.
