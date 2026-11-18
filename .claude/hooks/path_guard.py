#!/usr/bin/env python3
"""PreToolUse hook: keep a module agent inside its module (spec 12.1). Early warning only.

The module comes from the untracked file `.hmx-module` in the worktree root (written by
scripts/new_module_worktree.sh). No such file = coordinator checkout: nothing is blocked, edits to
shared contracts only produce a warning. The real enforcement is scripts/check_ownership.py in CI,
because this hook cannot see shell edits (`sed -i`, redirects).

Exit 2 + stderr = block (the message goes back to the agent); otherwise exit 0. Any internal error
allows the edit and warns, so a broken guard never wedges a session.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import ownership_lib as lib  # noqa: E402


def repo_root(cwd: Path) -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True, check=True
    )
    return Path(out.stdout.strip()).resolve()


def main() -> int:
    try:
        data = json.load(sys.stdin)
        tool_input = data.get("tool_input") or {}
        file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not file_path:
            return 0
        root = repo_root(Path(data.get("cwd") or os.getcwd()))
        try:
            rel = Path(file_path).resolve().relative_to(root).as_posix()
        except ValueError:
            return 0  # outside this repository: not our business
        marker = root / ".hmx-module"
        module = marker.read_text().strip() if marker.exists() else None
        config = lib.parse_simple_yaml((root / ".claude" / "ownership.yaml").read_text())
        decision, message = lib.hook_decision(config, module, rel)
        if decision == "block":
            print(message, file=sys.stderr)
            return 2
        if decision == "warn":
            print(json.dumps({"systemMessage": message}))
        return 0
    except Exception as exc:  # noqa: BLE001  fail open on purpose
        print(json.dumps({"systemMessage": f"path guard error, edit allowed: {exc}"}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
