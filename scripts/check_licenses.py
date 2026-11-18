#!/usr/bin/env python3
"""Fail if an installed runtime dependency has a licence outside the allowlist.

Allowlist and the one documented exception (homematicip, GPL-3.0-or-later) are defined in
intent/homematic-exporter.intent.md and docs/sbom/components.md. Run after
`pip install -r requirements.txt`.
"""

import re
import sys
from importlib.metadata import PackageNotFoundError, metadata
from pathlib import Path

ALLOWED = re.compile(
    r"^(mit|bsd(-[0-9]-clause)?|apache(-2\.0)?|isc|psf(-2\.0)?|python software foundation|"
    r"mpl(-2\.0)?|mozilla public license 2\.0)\b",
    re.IGNORECASE,
)
# Licence-name fragments to ignore when they are just decoration of an allowed name.
NOISE = re.compile(r"\b(license|licence|software|version|v)\b|[()]", re.IGNORECASE)
EXCEPTIONS = {"homematicip": "GPL-3.0-or-later (owner decision, see SBOM licence decision)"}
SPLIT = re.compile(r"\s+(?:AND|OR)\s+|;|,", re.IGNORECASE)


def requirement_names(path: Path) -> list[str]:
    names = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            names.append(re.split(r"[=<>!~\[ ]", line, maxsplit=1)[0])
    return names


def licence_of(name: str) -> str:
    md = metadata(name)
    expr = md.get("License-Expression")
    if expr:
        return expr
    lic = (md.get("License") or "").strip()
    if lic and len(lic) < 100 and "\n" not in lic:
        return lic
    classifiers = [
        c.split("::")[-1].strip() for c in md.get_all("Classifier") or [] if "License ::" in c
    ]
    return " AND ".join(classifiers) or "UNKNOWN"


def is_allowed(licence: str) -> bool:
    tokens = [t.strip() for t in SPLIT.split(licence) if t.strip()]
    if not tokens:
        return False
    for token in tokens:
        cleaned = NOISE.sub(" ", token)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not (ALLOWED.match(cleaned) or ALLOWED.match(token)):
            return False
    return True


def main() -> int:
    req = Path(sys.argv[1] if len(sys.argv) > 1 else "requirements.txt")
    bad = []
    for name in requirement_names(req):
        try:
            lic = licence_of(name)
        except PackageNotFoundError:
            bad.append((name, "NOT INSTALLED"))
            continue
        if name.lower() in EXCEPTIONS:
            print(f"EXCEPTION {name}: {lic} -> {EXCEPTIONS[name.lower()]}")
        elif is_allowed(lic):
            print(f"ok        {name}: {lic}")
        else:
            bad.append((name, lic))
    for name, lic in bad:
        print(f"NOT ALLOWED {name}: {lic}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
