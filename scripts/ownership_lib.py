"""Pure helpers for module ownership (spec 12.1). Standard library only (PyYAML optional).

Used by scripts/check_ownership.py (CI) and .claude/hooks/path_guard.py (Claude Code hook).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

BRANCH_RE = re.compile(r"^(?:feat|fix)/(?P<module>[a-z]+)(?:[-/].*)?$")


def glob_to_regex(glob: str) -> re.Pattern[str]:
    """`**` matches across directories, `*` and `?` stay within one path segment."""
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += ".*"
            i += 2
        elif glob[i] == "*":
            out += "[^/]*"
            i += 1
        elif glob[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(glob[i])
            i += 1
    return re.compile(f"^{out}$")


def matches(path: str, globs: Iterable[str]) -> bool:
    return any(glob_to_regex(g).match(path) for g in globs)


def module_for_branch(branch: str, modules: Iterable[str]) -> str | None:
    m = BRANCH_RE.match(branch)
    if m and m.group("module") in set(modules):
        return m.group("module")
    return None


def _scalar(text: str) -> Any:
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        return t[1:-1]
    return int(t) if t.isdigit() else t


def _flow_list(text: str) -> list[Any]:
    inner = text.strip()[1:-1].strip()
    return [_scalar(p) for p in inner.split(",") if p.strip()] if inner else []


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the restricted subset used by ownership.yaml (see that file's header)."""
    rows: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        rows.append((len(raw) - len(raw.lstrip()), raw.strip()))

    def block(i: int, indent: int) -> tuple[Any, int]:
        if rows[i][1].startswith("- "):
            items: list[Any] = []
            while i < len(rows) and rows[i][0] == indent and rows[i][1].startswith("- "):
                items.append(_scalar(rows[i][1][2:]))
                i += 1
            return items, i
        mapping: dict[str, Any] = {}
        while i < len(rows) and rows[i][0] == indent and not rows[i][1].startswith("- "):
            key, _, rest = rows[i][1].partition(":")
            key, rest = key.strip(), rest.strip()
            i += 1
            if rest.startswith("["):
                mapping[key] = _flow_list(rest)
            elif rest:
                mapping[key] = _scalar(rest)
            elif i < len(rows) and rows[i][0] > indent:
                mapping[key], i = block(i, rows[i][0])
            else:
                mapping[key] = None
        return mapping, i

    result, _ = block(0, rows[0][0]) if rows else ({}, 0)
    assert isinstance(result, dict)
    return result


def check_changes(config: Mapping[str, Any], branch: str, changed: Sequence[str]) -> list[str]:
    """Return violation messages for the files a branch changes (empty list = OK)."""
    problems: list[str] = []
    modules: Mapping[str, Sequence[str]] = config.get("modules", {})
    module = module_for_branch(branch, modules)
    if module:
        allowed = modules[module]
        outside = [f for f in changed if not matches(f, allowed)]
        if outside:
            problems.append(
                f"branch '{branch}' (module '{module}') may only change {list(allowed)}; "
                f"outside: {sorted(outside)}. Put change requests in specs/plans/{module}.md."
            )
    contracts = [f for f in changed if matches(f, config.get("contract_files", []))]
    if contracts:
        missing = [r for r in config.get("contract_requires", []) if r not in changed]
        if missing:
            problems.append(f"contract change {contracts} needs {missing} in the same PR")
        code = [f for f in changed if matches(f, config.get("module_code", []))]
        if code:
            problems.append(
                f"contract change {contracts} must be its own small PR; also changes {sorted(code)}"
            )
    return problems


def sections_changed(
    base: Mapping[str, Any], head: Mapping[str, Any], sections: Iterable[str]
) -> list[str]:
    return [s for s in sections if base.get(s) != head.get(s)]


def hook_decision(config: Mapping[str, Any], module: str | None, rel_path: str) -> tuple[str, str]:
    """Decide for one edit: ("allow"|"block"|"warn", message). `module` None = coordinator."""
    if module is None:
        if matches(rel_path, config.get("contract_files", [])):
            return (
                "warn",
                f"{rel_path} is a shared contract: change it in its own small PR together with "
                "specs/spec.md (spec 12.1).",
            )
        return ("allow", "")
    modules: Mapping[str, Sequence[str]] = config.get("modules", {})
    if module not in modules:
        return ("block", f"unknown module '{module}' in .hmx-module; known: {sorted(modules)}")
    if matches(rel_path, modules[module]):
        return ("allow", "")
    return (
        "block",
        f"Blocked: the '{module}' agent may not edit {rel_path}. Allowed: {list(modules[module])}. "
        f"Write the change request under 'Requests' in specs/plans/{module}.md and stop "
        "(spec 12.1).",
    )
