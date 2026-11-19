# Plan: Task 2b - `metrics` module

- **Spec:** sections 3, 5.1, 6, R6-R10, R19-R21, C11
- **Branch:** `feat/metrics` (from merged `main`)
- **Depends on:** shared contracts only

## Files that change
| Path | Change |
|---|---|
| `src/homematic_exporter/metrics/config.py` | `AppConfig` (composes `Tuning`, `ExtractConfig`, metric definitions), `load_config(path: Path | None = None)` with the R21 resolution (explicit path must exist; `None` = mount path then bundled default; never reads the environment), startup validation errors with key paths (R19) |
| `src/homematic_exporter/metrics/registry.py` | `Registry.build(metric_defs, tuning, version)`/`update/record_success/record_error/exposition`, `render(config, snapshot, batteries, version)`; private `CollectorRegistry`; series removal; derived (6.5) and meta (6.6) metrics; `data_age` absent before first success |
| `src/homematic_exporter/metrics/schema.py` | `MetricDef`, `Transform` (structural pydantic models), `validate_metrics` (semantic checks with key paths), `ConfigError` (added: keeps `config.py` and `registry.py` small and shares the checks between `load_config` and `Registry.build`) |
| `src/homematic_exporter/metrics/text.py` | `clean_text` (label/version/help sanitising), `NAME_PATTERN`, `echo_text` (= `escape_text` + `hide_tokens`, for anything echoed in an error; added) |
| `src/homematic_exporter/metrics/series.py` | pure label/value computation per metric (added) |
| `config/default-config.yaml` | **only the `metrics:` list** (spec 6.2-6.4); `extract`/`tuning` are fixed |
| `tests/metrics/` | hand-built `Snapshot` golden exposition (`golden/default_config.prom`), validation errors, extras-only metric, fallback order, hostile YAML, concurrency |

## Order of work
1. Validation tests for every R19 error class (with key path), then `load_config`.
2. Registry tests with a hand-built `Snapshot` (scale, transforms, series removal, `None` handling, cardinality), then `Registry`.
3. Fill the `metrics:` list and add the golden exposition file.

## Risks
- The integration golden test (fixture through the parser) is **not** this task (task 4).
- A raw-field typo silently produces no series (C11): log a warning for a metric with zero series on two consecutive updates.

## Proof
gate output plus a golden exposition file reviewed by the owner.

## Rules (spec 12.1)
- Edit only `src/homematic_exporter/metrics/`, `tests/metrics/`, this plan, and the `metrics:` list of `config/default-config.yaml`.
- Do not edit contracts (`contracts.py`, `config_models.py`, `redact.py`), the spec, `pyproject.toml`, root `CLAUDE.md`, `Dockerfile`, `.github/`, `docs/`, `requirements*.txt`, `tests/conftest.py`. Put change requests under "Requests" and stop.
- Cross-module imports only `contracts`, `config_models`, `redact` (`tests/test_import_boundaries.py`).
- Tests first; paste gate output (`ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`).

## Closing review task (mandatory, last task of this plan; specs/plan.md section A)
The PR is not opened until every step is done or marked n/a with a reason. Paste each verdict into the PR description. After any HIGH/CRITICAL fix the same reviewer re-checks.
- [x] R1 Gate (pip-audit and check_licenses clean; output in the PR description): `ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`, `pip-audit`, `check_licenses.py` (output pasted)
- [ ] R2 `python-reviewer`
- [ ] R3 `code-reviewer`
- [ ] R4 `security-reviewer`
- [ ] R5 `architect`: conditional: only if a contract change was requested or shared types touched
- [ ] R6 `code-simplifier` (after R2-R5 are clean; gate re-run)
- [ ] R7 `performance-optimizer`: conditional: registry update and exposition on a large snapshot
- [ ] R8 n/a: tests only (no app yet)
- [ ] R9 `doc-updater`: `CLAUDE.md`, module `CLAUDE.md`, SBOM manifest, spec catalogue in sync
- [ ] R10 owner PR review and squash merge

## Deviations from this plan
- Three files were added (`schema.py`, `series.py`, `text.py`: label/help sanitising, `NAME_PATTERN`, error-text escaping and token redaction), see the table.
- `Registry.build` gained a keyword-only `clock` (default `time.time`) for tests; `parse_config(raw)` and `ConfigError` are exported next to `load_config`.
- Steps 1-3 done in order; the default `metrics:` list holds the 14 entity metrics of 6.2-6.4.

- R21 fallback targets beyond the mount path: `/app/default-config.yaml` (image) and the repo copy `config/default-config.yaml` (`CHECKOUT_CONFIG_PATH`, found via `parents[3]`, for checkouts). A mount path that is a dangling symlink or unreadable never falls back.
- `scale != 1` is only valid with transform `none`; `state_retention_days` is capped at 36500 here; `version` must be the integer 1.
- Bounds added: config file 256 KiB (changed from 1 MiB), more than 500 metrics / 2000 `extract` entries / 20 top-level keys fail before pydantic, only 20 issues are scrubbed (`ConfigError.total` keeps the count), labels 200 characters, `version` 100.
- Process note: the hostile-input tests of the first pass (unhashable keys, NUL, huge integers) landed with or after their fixes, not red first. The fix-round tests (`test_hardening.py`) were committed red first.
- Fix-round decisions: label/version sanitising in `text.py`; the 256 KiB limit bounds the parse time of a hostile file to the measured worst case of about 2.3 to 2.6 s (flow sequences, about 10 ms per KiB); a 1 MiB file is refused before parsing.

- Fix round 2 (tests red first in `test_hardening2.py`): token redaction never touches strings that fully match the metric name pattern and now also covers messages (value after `=` too); LRM/RLM/ALM are cleaned; `quote()` keeps its closing quote; ENOTDIR and dangling symlinks count as a present (broken) mount; the YAML cost comment states the measured worst case (about 10 ms per KiB, about 2.3 to 2.6 s at the 256 KiB cap).

## Requests (to the coordinator)
1. `config_models.Tuning.state_retention_days` has no upper bound (`ge=1` only); `timedelta(days=10**30)` in `state` raises `OverflowError`. `metrics` rejects values above 36500 when loading, but the contract should carry the bound (`le=36500`) with a spec 5.1 note.
2. Spec section 3 (`metrics` row) and `docs/sbom/components.md`: mention `parse_config`, `ConfigError`, the `clock` keyword and that `scale` is valid with transform `none` only (spec 6.1 validation list).
3. `config/default-config.yaml` header comment still says the `metrics` list "is filled by the `metrics` task"; it sits outside the metrics list, so it is left for the coordinator.
4. Spec 6.6 does not say whether `homematic_last_successful_poll_timestamp_seconds` and `homematic_poll_duration_seconds` exist before the first success; this module omits both (like `data_age`). Confirm or change.

### Exact text for the coordinator
Spec-only PR (no shared contract file touched):
- Section 3, `metrics` row: the module exports `load_config`, `parse_config`, `AppConfig`, `ConfigError`, `MetricDef`, `Transform`, `Registry`, `render`. `Registry.build(metric_defs, tuning, version="dev", *, clock=time.time)` raises `ConfigError` for invalid definitions. `record_success(timestamp, duration)` raises `ValueError` for a timestamp outside [0, 4102444800] or a negative or non-finite duration. `app` calls build/update/exposition/record_success/record_error and never computes meta metrics.
- 6.1 validation list: name pattern `^homematic_[a-z0-9]+(_[a-z0-9]+)+$` (also fix the pattern comment in the 6.1 YAML sample); reserved built-in names; no `_total` suffix on gauges; help 1-500 characters; name and value up to 200; at most 3 labels, no duplicates, only those available for the scope; `in` up to 64 members; finite operands; `scale` only with transform `none`; `version` must be the integer 1; size caps: file 256 KiB, 500 metrics, 2000 entries per `extract` section, 20 top-level keys; 20 issues shown with the true total; `state_retention_days` at most 36500.
- Transform semantics: `none` accepts finite numbers and bools (text gives no series), `bool` accepts a bool or a finite number (0 is 0, other 1; text gives no series), `equals`/`in` compare by type (bool, number and text never equal each other); a non-finite result gives no series.
- Text sanitising: control and C1 characters, lone surrogates, U+2028/2029 and bidi controls (incl. LRM, RLM, ALM) become spaces; label values are capped at 200, help at 500, `version` at 100; ZWJ and umlauts are kept. Entities whose label values become equal after cleaning count as duplicates and the first is kept (one warning per metric).
- 6.6: `homematic_last_successful_poll_timestamp_seconds` and `homematic_poll_duration_seconds` are absent before the first success (like `data_age`); the duration is that of the last successful poll; the `build_info` version is cut at 100 characters.
- C11: the zero-series warning fires only when the scope had entities.
- R21: the chain is explicit path (must exist), `/etc/homematic-exporter/config/config.yaml`, `/app/default-config.yaml`, the repo copy (checkouts); a mount path that is a dangling symlink, behind an unreadable parent, below a regular file or itself broken fails and never falls back.
- 5.1 sample: help strings of `homematic_room_humidity_ratio` ("Room relative humidity (0-1)") and `homematic_room_window_open` ("1 if the room window is open or tilted") match the shipped default config.

Needs a shared contract change (own small PR, with spec): `Tuning.state_retention_days` upper bound (`le=36500`) in `config_models.py`; until then `parse_config` enforces it.
