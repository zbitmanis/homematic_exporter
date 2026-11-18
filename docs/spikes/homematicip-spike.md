---
package: homematicip
version: 2.23.1
python: 3.13   # inspected on 3.13; target is 3.12 (2.x requires >=3.12). NOT yet re-checked on 3.12
resolved_with: pip install in a python3.13 venv
date: 2026-11-18
sources: [installed package source, package metadata]
latest_on_pypi: 2.23.1 (release date not checked)
live_verified: true   # snapshot only (state download); websocket not exercised
---
# Spike: `homematicip` library fit

Date: 2026-11-18. Method: installed in isolated venvs, read the source. **No live access point was available**, so nothing here is verified against real data.

## Verdict
Use `homematicip` **2.23.1** on Python 3.12 (its minimum). Proceed to Design, but confirm with a recorded fixture from the real access point before the metric catalogue is finalised.

## Findings
| Question | Result |
|---|---|
| Maintained? | 2.23.1 is current on PyPI; requires Python >=3.12 (matches our target). 1.1.5 (Python 3.9+) is the old line; pin 2.x. |
| Async? | Yes: `async_home.py` (`init_async`, `get_current_state_async`, `enable_events`, websocket handler with reconnect helpers). Fits the asyncio poll loop. |
| Floor heating controller (12 valves) | `FloorTerminalBlock12` device; per-zone `FloorTerminalBlockMechanicChannel` / `...LocalPumpChannel` carry `valvePosition`. Zone-to-room mapping to confirm on fixture. |
| Radiator thermostats | `HeatingThermostat`, `...Compact`, `...Evo`: `valvePosition`, `setPointTemperature`, `valveActualTemperature`. |
| Wall thermostats + humidity | `WallMountedThermostatPro`, `...BasicHumidity`: `actualTemperature`, `humidity`, `setPointTemperature`. |
| Door sensor | `ShutterContact*` classes. |
| Room-level heating | `HeatingGroup`: `actualTemperature`, `setPointTemperature`, `valvePosition`, window state. |
| Boiler state | `HeatingCoolingDemandBoilerGroup.on` and `...PumpGroup.on` exist; whether this installation populates them is unknown (intent Q5). |
| Battery | Only `lowBat` (bool), `unreach` (bool), `rssiDeviceValue`, `deviceUndervoltage` (bool). **No battery voltage or percentage.** Confirms intent Q6: low-since and last-replaced tracking in `state/` is the main early-warning signal; `deviceUndervoltage` and `unreach` are extra early signals. |

## Risks
1. **Licence: GPL-3.0-or-later.** Decision (2026-11-18): this repo is MIT; the public image is distributed under GPL terms for the combined work. See SBOM "Licence decision" and `THIRD_PARTY_NOTICES.md`.
2. Unofficial cloud API: can change without notice; pin the version and keep `Source` behind the protocol so a local CCU client remains possible.
3. Pins were resolved on Python 3.13; verify on 3.12 in CI.
4. Library pulls `httpx2` and `opentelemetry-api` transitively; larger dependency surface than a hand-written client.

## Next (needs your access point)
Run a one-off script to authenticate (access-point button + PIN), dump `get_current_state_async` as JSON, scrub SGTINs/PIN/token, and save as `tests/source/fixtures/`. That closes intent Q2, Q3 (poll vs websocket), Q5 and Q7.

## Live snapshot results (2026-11-18, scrubbed fixture kept local, git-ignored)
- 20 devices, 12 `HEATING` rooms. Battery signals present on every device; radiator valves report `valvePosition`; FALMOT channels 1-11 map to rooms, channel 12 unused.
- Boiler/pump demand groups exist but report `on`/`heatDemand` = `None`; derive heat demand from valve positions (intent Q5).
- Device labels repeat; use `<room> <model>` (intent Q7).
- One device currently has `lowBat = true` (an HmIP-STHD display sensor): a real alert candidate for the first release.
- Fixture is git-ignored; tests need a small hand-written fixture derived from it (CLAUDE.md note below).

