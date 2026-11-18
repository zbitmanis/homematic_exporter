#!/usr/bin/env python3
"""PreToolUse hook: keep a module agent inside its module (spec 12.1). Early warning only.

The module comes from the untracked file `.hmx-module` in the worktree root (written by
scripts/new_module_worktree.sh). No such file = coordinator checkout: nothing is blocked, edits to
shared contracts only produce a warning. The real enforcement is scripts/check_ownership.py in CI,
because this hook cannot see shell edits (`sed -i`, `rm .hmx-module`, redirects).

The repository root is this file's own checkout (not the payload's cwd). For a module agent the hook
fails CLOSED: any error, any path outside the worktree (except temp dirs) and any symlink that
escapes the worktree is blocked. For the coordinator it fails open with a warning, so a broken guard
never wedges a session.

Exit 2 + stderr = block (the message goes back to the agent); otherwise exit 0.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import ownership_lib as lib  # noqa: E402

TEMP_DIRS = {os.path.realpath(d) for d in (tempfile.gettempdir(), "/tmp", "/private/tmp")}  # noqa: S108


def relative_to_root(path: str) -> str | None:
    """Path relative to ROOT, comparing by identity (case-insensitive file systems, symlinks)."""
    parts = Path(path).parts
    for i in range(len(parts), 0, -1):
        candidate = Path(*parts[:i])
        if candidate.exists() and ROOT.exists() and os.path.samefile(candidate, ROOT):
            return Path(*parts[i:]).as_posix() if parts[i:] else "."
    return None


def in_other_checkout(path: str) -> bool:
    """True if `path` is inside a checkout of this project (marker/ownership file above it)."""
    for parent in Path(path).parents:
        if (parent / ".hmx-module").exists() or (parent / ".claude" / "ownership.yaml").exists():
            return True
    return False


def in_temp(path: str) -> bool:
    """Temp files are fine (scratchpads), but never another worktree that happens to live in /tmp."""
    real = os.path.realpath(path)
    in_tmp = any(real == t or real.startswith(t + os.sep) for t in TEMP_DIRS)
    return in_tmp and not in_other_checkout(real)


def decide() -> tuple[int, str]:
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not file_path:
        return 0, ""
    cwd = Path(data.get("cwd") or os.getcwd())
    lexical = os.path.normpath(str(cwd / file_path))  # what the agent named, symlinks not followed
    marker = ROOT / ".hmx-module"
    module = marker.read_text().strip() if marker.exists() else None
    config = lib.parse_simple_yaml((ROOT / ".claude" / "ownership.yaml").read_text())
    lib.validate_config(config)

    rel = relative_to_root(lexical)
    if rel is None:
        if module and not in_temp(lexical):
            return 2, (
                f"Blocked: the '{module}' agent may not edit {lexical}: outside your worktree "
                f"({ROOT}). Work only inside your own worktree (spec 12.1)."
            )
        return 0, ""
    real = os.path.realpath(lexical)
    if module and real != lexical:  # a symlink somewhere on the path
        if relative_to_root(real) is None and not in_temp(real):
            return 2, f"Blocked: {lexical} resolves to {real}, outside your worktree (symlink)."
    decision, message = lib.hook_decision(config, module, rel)
    if module and real != lexical:  # the symlink target inside the repo must be allowed too
        target_rel = relative_to_root(real)
        if target_rel is not None:
            target_decision, target_message = lib.hook_decision(config, module, target_rel)
            if target_decision == "block":
                return 2, target_message
    if decision == "block":
        return 2, message
    if decision == "warn":
        return 0, json.dumps({"systemMessage": message})
    return 0, ""


def main() -> int:
    try:
        code, message = decide()
    except Exception as exc:  # noqa: BLE001
        if (ROOT / ".hmx-module").exists():
            msg = f"Blocked: path guard error for a module agent (failing closed): {exc}"
            print(msg, file=sys.stderr)
            return 2
        print(json.dumps({"systemMessage": f"path guard error, edit allowed: {exc}"}))
        return 0
    if code == 2:
        print(message, file=sys.stderr)
    elif message:
        print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
