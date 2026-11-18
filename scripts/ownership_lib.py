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


def _strip_comment(text: str) -> str:
    """Drop a trailing `# comment` that sits outside quotes (a `#` must follow whitespace)."""
    quote = ""
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text.rstrip()


def _scalar(text: str) -> Any:
    t = text.strip()
    if not t:
        return None
    if t[0] in "\"'":
        q = t[0]
        out, i = "", 1
        while i < len(t):
            ch = t[i]
            if q == '"' and ch == "\\" and i + 1 < len(t):
                out += t[i + 1]
                i += 2
            elif ch == q:
                if q == "'" and t[i + 1 : i + 2] == "'":
                    out += "'"
                    i += 2
                elif i == len(t) - 1:
                    return out
                else:
                    raise ValueError(f"unexpected text after closing quote: {text!r}")
            else:
                out += ch
                i += 1
        raise ValueError(f"unterminated quote: {text!r}")
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    if t in ("null", "~"):
        return None
    return int(t) if t.isdigit() else t


def _flow_list(text: str) -> list[Any]:
    inner = text.strip()
    if not (inner.startswith("[") and inner.endswith("]")):
        raise ValueError(f"unterminated flow list: {text!r}")
    inner = inner[1:-1]
    items: list[str] = []
    cur, quote = "", ""
    for ch in inner:
        if quote:
            cur += ch
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch == ",":
            items.append(cur)
            cur = ""
        else:
            cur += ch
    if quote:
        raise ValueError(f"unterminated quote in flow list: {text!r}")
    items.append(cur)
    return [_scalar(p) for p in items if p.strip()]


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the restricted subset used by ownership.yaml (see that file's header).

    Anything outside the subset raises ValueError instead of being mis-read: tabs, unterminated
    quotes, lists at the same indent as their key, `- key: value` items, duplicate keys, a root that
    is not a mapping.
    """
    rows: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if raw[: len(raw) - len(raw.lstrip())].count("\t"):
            raise ValueError(f"tab indentation is not supported: {raw!r}")
        body = _strip_comment(raw.strip())
        if body:
            rows.append((len(raw) - len(raw.lstrip()), body))

    def block(i: int, indent: int) -> tuple[Any, int]:
        if rows[i][1].startswith("- "):
            items: list[Any] = []
            while i < len(rows) and rows[i][0] == indent and rows[i][1].startswith("- "):
                item = rows[i][1][2:]
                if item.lstrip()[:1] not in "\"'" and ": " in item + " ":
                    raise ValueError(f"mappings inside lists are not supported: {item!r}")
                items.append(_scalar(item))
                i += 1
            return items, i
        mapping: dict[str, Any] = {}
        while i < len(rows) and rows[i][0] == indent and not rows[i][1].startswith("- "):
            key, sep, rest = rows[i][1].partition(":")
            if not sep:
                raise ValueError(f"expected 'key: value', got {rows[i][1]!r}")
            key, rest = key.strip(), rest.strip()
            if key in mapping:
                raise ValueError(f"duplicate key {key!r}")
            i += 1
            if rest.startswith("["):
                mapping[key] = _flow_list(rest)
            elif rest:
                mapping[key] = _scalar(rest)
            elif i < len(rows) and rows[i][0] > indent:
                mapping[key], i = block(i, rows[i][0])
            elif i < len(rows) and rows[i][0] == indent and rows[i][1].startswith("- "):
                raise ValueError(f"list under {key!r} must be indented")
            else:
                mapping[key] = None
        if i < len(rows) and rows[i][0] > indent:
            raise ValueError(f"unexpected indentation: {rows[i][1]!r}")
        return mapping, i

    if not rows:
        return {}
    result, end = block(0, rows[0][0])
    if not isinstance(result, dict) or end != len(rows):
        raise ValueError("the document root must be a mapping")
    return result


def validate_config(config: Mapping[str, Any]) -> None:
    """Raise ValueError for rules that would silently never match."""
    groups = [*config.get("modules", {}).values(), config.get("contract_files", []),
              config.get("contract_requires", []), config.get("module_code", [])]  # fmt: skip
    for group in groups:
        for glob in group:
            if not isinstance(glob, str) or not glob or glob.endswith("/"):
                raise ValueError(f"invalid glob {glob!r} (use `dir/**`, no trailing slash)")
            if re.search(r"[^/]\*\*|\*\*[^/]", glob.replace("**/", "").replace("/**", "")):
                raise ValueError(f"`**` must be a whole path segment: {glob!r}")


def _prefixed_module_token(branch: str, modules: Iterable[str]) -> str | None:
    """A feat/ or fix/ branch whose first token merely looks like a module name (state2, State)."""
    m = re.match(r"^(?:feat|fix)/([^-/]+)", branch)
    if not m:
        return None
    token = m.group(1)
    names = set(modules)
    if token in names:
        return None
    return token if any(token.lower().startswith(n) for n in names) else None


def check_changes(config: Mapping[str, Any], branch: str, changed: Sequence[str]) -> list[str]:
    """Return violation messages for the files a branch changes (empty list = OK)."""
    problems: list[str] = []
    modules: Mapping[str, Sequence[str]] = config.get("modules", {})
    module = module_for_branch(branch, modules)
    lookalike = _prefixed_module_token(branch, modules)
    if lookalike:
        problems.append(
            f"branch '{branch}' looks like a module branch but '{lookalike}' is not exactly one of "
            f"{sorted(modules)}; name it feat/<module> or fix/<module>[-text] (or pick a name that "
            "does not start with a module name)"
        )
    if module:
        allowed = modules[module]
        outside = [f for f in changed if not matches(f, allowed)]
        if outside:
            problems.append(
                f"branch '{branch}' (module '{module}') may only change {list(allowed)}; "
                f"outside: {sorted(outside)}. Put change requests in specs/plans/{module}.md."
            )
    prefixes = config.get("branch_prefixes", ["feat/", "fix/"])
    if not any(branch.startswith(p) for p in prefixes):
        problems.append(f"branch '{branch}' must start with one of {list(prefixes)}")
    contracts = [f for f in changed if matches(f, config.get("contract_files", []))]
    if contracts:
        missing = [r for r in config.get("contract_requires", []) if r not in changed]
        if missing:
            problems.append(f"contract change {contracts} needs {missing} in the same PR")
    return problems


def warnings_for(config: Mapping[str, Any], changed: Sequence[str]) -> list[str]:
    """Advice that does not fail the check (a breaking contract change must also fix callers)."""
    contracts = [f for f in changed if matches(f, config.get("contract_files", []))]
    code = [f for f in changed if matches(f, config.get("module_code", []))]
    if contracts and code:
        return [
            f"contract change {contracts} also changes module code {sorted(code)}; prefer a small "
            "contract PR merged first unless the change is breaking and the callers must move with it"
        ]
    return []


def sections_outside(
    base: Mapping[str, Any], head: Mapping[str, Any], allowed: Iterable[str]
) -> list[str]:
    """Top-level sections that differ between base and head, except the allowed ones."""
    keys = (set(base) | set(head)) - set(allowed)
    return sorted(k for k in keys if base.get(k) != head.get(k))


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
