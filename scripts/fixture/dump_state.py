#!/usr/bin/env python3
"""SPIKE TOOL (throwaway): dump and scrub the Homematic IP state for use as a test fixture.

Credentials come from the environment, never from arguments or files:
    HMIP_ACCESS_POINT   24-character SGTIN of the access point
    HMIP_AUTH_TOKEN     token from `hmip_generate_auth_token`
Output (default dir tests/source/fixtures/):
    state.scrubbed.json   scrubbed raw state; REVIEW BEFORE COMMITTING
    state.summary.md      device/group inventory and which heating/battery fields exist
Read-only: only downloads the configuration, never writes to the heating system.
"""

import asyncio
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

SGTIN_RE = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{24}(?![0-9A-Za-z])")
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
DROP_KEYS = {"clients", "authToken", "pin", "clientAuthToken", "clientId"}
LOCATION_KEYS = {"city", "latitude", "longitude", "location", "timeZoneId"}
HEATING_FIELDS = (
    "actualTemperature",
    "setPointTemperature",
    "valvePosition",
    "valveActualTemperature",
    "humidity",
    "lowBat",
    "unreach",
    "rssiDeviceValue",
    "deviceUndervoltage",
)


class Scrubber:
    """Replaces SGTINs, UUIDs and MACs with stable placeholders so cross-references survive."""

    def __init__(self, secrets: list[str]):
        self.secrets = [s for s in secrets if s]
        self.maps: dict[str, dict[str, str]] = {"SGTIN": {}, "ID": {}, "MAC": {}}

    def _ph(self, kind: str, value: str) -> str:
        m = self.maps[kind]
        return m.setdefault(value, f"{kind}-{len(m) + 1:04d}")

    def text(self, s: str) -> str:
        for secret in self.secrets:
            s = s.replace(secret, "REDACTED")
        s = SGTIN_RE.sub(lambda m: self._ph("SGTIN", m.group()), s)
        s = UUID_RE.sub(lambda m: self._ph("ID", m.group().lower()), s)
        return MAC_RE.sub(lambda m: self._ph("MAC", m.group().upper()), s)

    def walk(self, node):
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k in DROP_KEYS:
                    continue
                key = self.text(k)
                out[key] = (
                    "REDACTED"
                    if k in LOCATION_KEYS and isinstance(v, (str, int, float))
                    else self.walk(v)
                )
            return out
        if isinstance(node, list):
            return [self.walk(v) for v in node]
        return self.text(node) if isinstance(node, str) else node


def summarize(raw: dict) -> str:
    lines = [
        "# Fixture summary (generated)",
        "",
        "## Devices",
        "",
        "| modelType | label | heating/battery fields present |",
        "|---|---|---|",
    ]
    for dev in raw.get("devices", {}).values():
        present = set()
        for ch in dev.get("functionalChannels", {}).values():
            present |= {f for f in HEATING_FIELDS if f in ch}
        lines.append(
            f"| {dev.get('modelType', dev.get('type'))} | {dev.get('label')} | {', '.join(sorted(present)) or '-'} |"
        )
    groups = Counter(g.get("type") for g in raw.get("groups", {}).values())
    lines += ["", "## Group types", ""] + [f"- {t}: {n}" for t, n in sorted(groups.items())]
    for g in raw.get("groups", {}).values():
        if g.get("type") in ("HEATING_COOLING_DEMAND_BOILER", "HEATING_COOLING_DEMAND_PUMP"):
            lines.append(f"- {g['type']} `on` = {g.get('on')} (label: {g.get('label')})")
    names = Counter(d.get("label") for d in raw.get("devices", {}).values())
    dup = [n for n, c in names.items() if c > 1]
    lines += [
        "",
        f"## Device-name uniqueness (intent Q7): {'DUPLICATES: ' + ', '.join(map(str, dup)) if dup else 'all unique'}",
    ]
    return "\n".join(lines) + "\n"


async def main() -> int:
    ap, token = os.environ.get("HMIP_ACCESS_POINT", ""), os.environ.get("HMIP_AUTH_TOKEN", "")
    if not ap or not token:
        print("Set HMIP_ACCESS_POINT and HMIP_AUTH_TOKEN", file=sys.stderr)
        return 2
    from homematicip.async_home import AsyncHome  # imported late so scrub logic is testable offline

    home = AsyncHome()
    await home.init_async(ap.replace("-", "").upper(), token)
    raw = await home.download_configuration_async()

    summary = summarize(raw)  # computed on raw names/fields only; scrubbed below
    scrub = Scrubber([token, ap, ap.replace("-", "").upper()])
    clean = scrub.walk(raw)
    summary = scrub.text(summary)

    blob = json.dumps(clean, indent=2, sort_keys=True)
    leaks = [s for s in scrub.secrets if s in blob]
    if leaks:
        print("Scrub failed: secret still present; nothing written", file=sys.stderr)
        return 1
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/source/fixtures")
    out.mkdir(parents=True, exist_ok=True)
    (out / "state.scrubbed.json").write_text(blob + "\n")
    (out / "state.summary.md").write_text(summary)
    print(f"Wrote {out}/state.scrubbed.json and state.summary.md. Review them before committing.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
