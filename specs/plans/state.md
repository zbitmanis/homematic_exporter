# Plan: Task 2a - `state` module

- **Spec:** sections 3, 8, R12-R14, C3, C4
- **Branch:** `feat/state` (from merged `main`)
- **Depends on:** shared contracts only

## Files that change
| Path | Change |
|---|---|
| `src/homematic_exporter/state/store.py` | `FileStateStore(dir)`: 0700 dir, 0600 files, atomic write, refuses looser permissions |
| `src/homematic_exporter/state/battery.py` | `BatteryHistory(store, tuning)` with `update(devices, now) -> list[BatteryRecord]` |
| `src/homematic_exporter/state/__init__.py` | exports |
| `tests/state/` | `tmp_path` tests |

## Order of work
1. Store tests (permissions, atomicity, missing/corrupt file), then store.
2. Battery tests following spec section 8 exactly (record created on first sight for every device, first sight low vs unreachable vs `None`, transitions, unreachable freeze but still seen, `last_seen_day` at day granularity with at most one extra write per day, prune by `tuning.state_retention_days`, returns only current devices, restart reload), then `BatteryHistory`.

## Risks
- A corrupt state file must not crash the poll loop: decide and test (log and start empty).
- Time is injected (`now`), never read inside the class.

## Proof
gate output plus the transition table covered by tests; no secrets or paths in exceptions.

## Rules (spec 12.1)
- Edit only `src/homematic_exporter/state/`, `tests/state/`, this plan.
- Do not edit contracts (`contracts.py`, `config_models.py`, `redact.py`), the spec, `pyproject.toml`, root `CLAUDE.md`, `Dockerfile`, `.github/`, `docs/`, `requirements*.txt`, `tests/conftest.py`. Put change requests under "Requests" and stop.
- Cross-module imports only `contracts`, `config_models`, `redact` (`tests/test_import_boundaries.py`).
- Tests first; paste gate output (`ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`).

## Closing review task (mandatory, last task of this plan; specs/plan.md section A)
The PR is not opened until every step is done or marked n/a with a reason. Paste each verdict into the PR description. After any HIGH/CRITICAL fix the same reviewer re-checks.
- [x] R1 Gate: `ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`, `pip-audit`, `check_licenses.py` (output pasted)
- [x] R2 `python-reviewer`: BLOCK (corrupt-file startup crash), fixed; re-checked twice, all fixed (last finding: `update` timestamp range vs load bounds)
- [x] R3 `code-reviewer`: APPROVE; spec section 8 implemented rule by rule; one MEDIUM (a failed save never retried) fixed
- [x] R4 `security-reviewer`: no path, permission or symlink flaw; found and fixed corrupt-file crashes, NaN/Infinity, FIFO hang, over-broad temp cleanup, fd leak, unchecked stored ranges; re-checked twice, all fixed
- [x] R5 `architect`: n/a, no contract change requested and no shared types touched
- [x] R6 `code-simplifier`: `update` and `load` split into helpers, behavior unchanged, gate re-run (358 tests)
- [x] R7 `performance-optimizer`: n/a, one synchronous write per day or change on about 20 devices; the `app` plan moves the blocking `fsync` off the event loop
- [x] R8 n/a: tests only (no app yet); FIFO, descriptor-leak and round-trip cases also reproduced by hand
- [x] R9 docs check (Haiku, doc-updater role): module docs done here; spec, SBOM and `app` plan updates in the separate docs PR (`feat/spec-state-clarifications`)
- [ ] R10 owner PR review and squash merge

## Requests (to the coordinator)
These are requests to the coordinator (separate docs PR).

- (a) spec section 8 / R12 / R14 clarifications: the stored format includes `room` and `device_type` (a change to either causes a save); `unreachable` None counts as reachable, also on first sight; "was low" means `low_since is not None`; R12 means the directory permissions (plus owner and non-directory checks); pruning keeps a record exactly N days old; malformed stored records are dropped; a failed save is retried on the next update; an invalid `now` raises `ValueError`.
- (b) app plan: construct `FileStateStore(STATE_DIR)` in `wiring.py` and map `StateDirError` to a non-zero exit with a path-free log line; pass `config.tuning`; call `update(devices, snapshot.taken_at)` from the single poll task; run the synchronous fsync write off the event loop (`asyncio.to_thread`); document that `update` never raises `OSError`.
- (c) deployment note: the state volume must be mode 0700 and owned by the container user (rootless podman: the `:U` volume option or equivalent); a private parent directory is recommended (the store does not create parents).
- (d) `docs/sbom/components.md` row for `state`: depends on "contracts, config_models" and lists `StateDirError`.
- (e) spec/deployment note: the state directory must be used by ONE process (single replica, no locking); a failing save is logged at most once per 15 minutes; special files and symlinks as state files are rejected.
