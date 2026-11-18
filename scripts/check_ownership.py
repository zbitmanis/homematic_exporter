#!/usr/bin/env python3
"""CI check: a PR may only change what its branch is allowed to change (spec 12.1).

Reads `.claude/ownership.yaml` from the BASE branch, so a PR cannot loosen its own limits.
If the base has no ownership file yet (the PR that introduces it), the check is skipped.

    python scripts/check_ownership.py --base origin/main --branch feat/state
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ownership_lib as lib  # noqa: E402
import yaml  # noqa: E402  (PyYAML is a pinned runtime dependency)

OWNERSHIP = ".claude/ownership.yaml"


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout


def _yaml_at(repo: Path, spec: str) -> dict[str, object]:
    try:
        return yaml.safe_load(git(repo, "show", spec)) or {}
    except subprocess.CalledProcessError:
        return {}  # file absent on that side


def _yaml_file(path: Path) -> dict[str, object]:
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--branch", required=True, help="PR head branch name")
    ap.add_argument("--repo", default=".")
    args = ap.parse_args(argv)
    repo = Path(args.repo)

    try:
        git(repo, "rev-parse", "--verify", "--quiet", f"{args.base}^{{commit}}")
    except subprocess.CalledProcessError:
        print(
            f"ownership violation: base ref {args.base!r} does not resolve (fetch it first)",
            file=sys.stderr,
        )
        return 1
    try:
        text = git(repo, "show", f"{args.base}:{OWNERSHIP}")
    except subprocess.CalledProcessError:
        print(f"notice: {args.base} has no {OWNERSHIP} (bootstrap); ownership check skipped")
        return 0
    try:
        config = lib.parse_simple_yaml(text)
        lib.validate_config(config)
    except ValueError as exc:
        print(f"ownership violation: {OWNERSHIP} on {args.base} is invalid: {exc}", file=sys.stderr)
        return 1

    # --no-renames: a rename must list BOTH the old and the new path (a move out of a protected
    # path would otherwise show only its allowed destination)
    diff = git(repo, "diff", "--name-only", "--no-renames", "-z", f"{args.base}...HEAD")
    changed = [f for f in diff.split("\0") if f]
    problems = lib.check_changes(config, args.branch, changed)
    for w in lib.warnings_for(config, changed):
        print(f"warning: {w}")

    module = lib.module_for_branch(args.branch, config.get("modules", {}))
    if module:
        for path, allowed in config.get("editable_sections", {}).items():
            if path in changed:
                base = _yaml_at(repo, f"{args.base}:{path}")
                head = _yaml_file(repo / path)
                bad = lib.sections_outside(base, head, allowed)
                if bad:
                    problems.append(
                        f"{path}: module branches may change only sections {allowed}; changed {bad}"
                    )

    if problems:
        for p in problems:
            print(f"ownership violation: {p}", file=sys.stderr)
        return 1
    scope = f"module '{module}'" if module else "coordinator branch"
    print(f"ownership ok: {len(changed)} changed file(s), {scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
