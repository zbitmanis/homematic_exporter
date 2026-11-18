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

OWNERSHIP = ".claude/ownership.yaml"


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return done.stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--branch", required=True, help="PR head branch name")
    ap.add_argument("--repo", default=".")
    args = ap.parse_args(argv)
    repo = Path(args.repo)

    try:
        config = lib.parse_simple_yaml(git(repo, "show", f"{args.base}:{OWNERSHIP}"))
    except subprocess.CalledProcessError:
        print(f"notice: {args.base} has no {OWNERSHIP}; ownership check skipped")
        return 0

    changed = [f for f in git(repo, "diff", "--name-only", f"{args.base}...HEAD").splitlines() if f]
    problems = lib.check_changes(config, args.branch, changed)

    module = lib.module_for_branch(args.branch, config.get("modules", {}))
    if module:
        import yaml  # PyYAML is a pinned runtime dependency

        for path, sections in config.get("protected_sections", {}).items():
            if path in changed:
                base = yaml.safe_load(git(repo, "show", f"{args.base}:{path}")) or {}
                head = yaml.safe_load((repo / path).read_text()) or {}
                bad = lib.sections_changed(base, head, sections)
                if bad:
                    problems.append(f"{path}: module branches must not change sections {bad}")

    if problems:
        for p in problems:
            print(f"ownership violation: {p}", file=sys.stderr)
        return 1
    scope = f"module '{module}'" if module else "coordinator branch"
    print(f"ownership ok: {len(changed)} changed file(s), {scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
