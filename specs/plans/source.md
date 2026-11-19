# Plan: Task 2c - `source` module

- **Spec:** sections 3, 4, R15, C1, C7
- **Branch:** `feat/source` (from merged `main`)
- **Depends on:** shared contracts only

## Files that change
| Path | Change |
|---|---|
| `src/homematic_exporter/source/parser.py` | `parse_snapshot(raw, now, extract, on_collision)` per spec section 4 |
| `src/homematic_exporter/source/file_source.py` | `FileSource(path, extract)`; both implement `Source.fetch(on_collision)`; the source logs one WARNING per new collision (names only) |
| `src/homematic_exporter/source/cloud.py` | `CloudSource(access_point, token, timeout, extract)` over `homematicip` 2.23.1 `AsyncHome`; builds `UpstreamError` with a body scrubbed by `redact.scrub` |
| `src/homematic_exporter/source/__init__.py` | (added) exports `CloudSource`, `FileSource`, `ParseReport`, `parse_snapshot`, `parse_with_report` |
| `tests/source/conftest.py` | (added) `extract_with_extras` fixture and `make_state`/`device` builders |
| `src/homematic_exporter/source/builder.py` | (added) `SnapshotBuilder`: parse + log each new collision / unmapped model once, shared by both sources |
| `tests/source/` | parser tests on the shared `tests/fixtures/mini_state.json` (+ `collision_state`; **do not edit the shared fixture**, request changes), `default_extract` fixture; `CloudSource` tests with a fake home object |

## Deviations from this plan and fix log
- Added `parse_with_report` (returns a `ParseReport`) next to `parse_snapshot`, `builder.py` (`SnapshotBuilder`) so the pure parser logs nothing and the sources log once, and keyword-only `clock` / `home_factory` on the constructors.
- **These are interface additions that need the spec PR**: the new public exports (`parse_with_report`, `ParseReport`, keyword-only `clock`/`home_factory`, `SnapshotBuilder`), the strict top-level payload check (`UpstreamError`), collisions resolved per kind (devices, valves, contacts, rooms), the floor-valve rule (exactly one room) and the up to 2x timeout per `fetch`. Existing spec signatures still work, but the spec does not describe these yet (see Requests).
- Decisions on open points are listed in `src/homematic_exporter/source/CLAUDE.md`.
- Fix round 1 (`52ac233`, `df70fa7`, `de464da`; after the R2-R4 reviews): errors carry no `__context__`; names sanitised and bounded; thin `UpstreamError` bodies filled; log scrub before cut; stripped credentials; escaped bodies; suffix reserves base names; first library import off the loop.
- Fix round 2 (`5814974`, `7e40c6f`): joiners kept in names (only Cc, Cs, Zl, Zp and bidi controls replaced); `_describe` uses `islice`; parser error bodies re-scrubbed with the credentials; cancellation during the first `home_factory()` tested.
- Fix round 3 (`4626e57`, 28c3389): LRM, RLM and ALM replaced; channel sort key uses `_channel_number`; module `CLAUDE.md` corrected.

## Order of work
1. Parser tests (rooms, device-to-room joins, naming, collision modes, valves, contacts, extras, `None` handling, unmapped model), then `parse_snapshot`.
2. `FileSource` tests, then `FileSource`.
3. `CloudSource` against a fake; no network, no real credentials.

## Risks
- `CloudSource` cannot be verified live in this task (first live run is a later review phase P8).
- The library is GPL-3.0: do not copy its code.
- Never log the token, access point or SGTINs.

## Proof
gate output; parser golden `Snapshot` for the fixture.

## Rules (spec 12.1)
- Edit only `src/homematic_exporter/source/`, `tests/source/`, this plan.
- Do not edit contracts (`contracts.py`, `config_models.py`, `redact.py`), the spec, `pyproject.toml`, root `CLAUDE.md`, `Dockerfile`, `.github/`, `docs/`, `requirements*.txt`, `tests/conftest.py`. Put change requests under "Requests" and stop.
- Cross-module imports only `contracts`, `config_models`, `redact` (`tests/test_import_boundaries.py`).
- Tests first; paste gate output (`ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`).

## Closing review task (mandatory, last task of this plan; specs/plan.md section A)
The PR is not opened until every step is done or marked n/a with a reason. Paste each verdict into the PR description. After any HIGH/CRITICAL fix the same reviewer re-checks.
- [x] R1 Gate: `ruff check .`, `ruff format --check .`, `mypy src tests`, `pytest -q`, `pip-audit`, `check_licenses.py` (output pasted)
- [ ] R2 `python-reviewer`
- [ ] R3 `code-reviewer`
- [ ] R4 `security-reviewer`
- [ ] R5 `architect`: conditional: only if a contract change was requested or shared types touched
- [ ] R6 `code-simplifier` (after R2-R5 are clean; gate re-run)
- [ ] R7 `performance-optimizer`: conditional: parser cost on the full capture size (about 130 KB)
- [ ] R8 n/a: tests only (no app yet)
- [ ] R9 `doc-updater`: `CLAUDE.md`, module `CLAUDE.md`, SBOM manifest, spec catalogue in sync
- [ ] R10 owner PR review and squash merge

## Requests (to the coordinator)
Spec text to add (section 3/4/C6/C7; the interface additions above are included), from the implementation:
- A device model is matched exactly against `extract.device_models`; an unmatched one becomes the cleaned, lowercased model and is reported once.
- Upstream names (room labels, unmapped models) are sanitised: control characters, lone surrogates, line/paragraph separators and bidi controls become spaces, the result is stripped and at most 128 characters.
- The suffix rule skips names already taken: an entity really called `a-2` keeps it, the suffixed `a` becomes `a-3`.
- A payload without a `devices` object and a `groups` object raises `UpstreamError` (strict top-level check); everything inside is lenient (`None`).
- Collisions are resolved per kind (devices, valves, contacts, rooms), rooms included.
- A floor-valve channel whose groups name zero or several rooms is skipped.
- One `CloudSource.fetch` can take up to 2x `HTTP_TIMEOUT_SECONDS` (separate timeouts for `init_async` and the download).
- Room labels: a room is a group of the configured  with a non-empty string label; the label is cleaned and cut to 128 characters; duplicate labels collide (like device names). A device in no room or in several takes the configured .
- A model is matched exactly; a missing or empty model becomes ; at most 256 distinct unmapped models are reported per source.
-  is raised for rooms, valves and contacts too, and lists at most 20 names. The  docstring and message say "device": a coordinator contract PR. The log covers all kinds.
- Tie-break for suffixes: SGTIN (no SGTIN first), then device id, then channel number (non-numeric or long keys last).
- The base channel is the first (by channel number) ,  or ;  accepts integral floats within +-1000.
- A floor valve needs exactly one labelled room in its channel's staff access_bpf everyone localaccounts _appserverusr admin _appserveradm _lpadmin com.apple.sharepoint.group.1 _appstore _lpoperator _developer _analyticsusers com.apple.access_ftp com.apple.access_screensharing com.apple.access_ssh com.apple.access_remote_ae; zero or several are skipped. The "channel 12 is unused" sentence is not implemented as such (an empty staff access_bpf everyone localaccounts _appserverusr admin _appserveradm _lpadmin com.apple.sharepoint.group.1 _appstore _lpoperator _developer _analyticsusers com.apple.access_ftp com.apple.access_screensharing com.apple.access_ssh com.apple.access_remote_ae list is what skips it).
- Extras: every configured key of the scope is present;  when missing, non-scalar or non-finite; strings pass through as-is.
-  limits: 8 MiB, regular files only,  on the final component, no paths in errors, / rejected, not for large files (memory).
- C7 accepted limits: the library logs error bodies and URLs itself (the app must scrub), trusts  from the lookup response, no size cap on the cloud response,  is never closed,  is not safe for concurrent calls.
- Library surfaces relied on: , , ,  (403),  (429), and the  text in  messages.
