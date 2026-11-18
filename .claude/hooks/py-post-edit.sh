#!/usr/bin/env bash
# PostToolUse: format and lint a Python file after an edit. Fast, file-scoped; mypy and full tests run at commit/PR.
set -u
f=$(jq -r '.tool_input.file_path // empty' 2>/dev/null) || exit 0
case "$f" in *.py) ;; *) exit 0 ;; esac
[ -f "$f" ] || exit 0
command -v ruff >/dev/null 2>&1 || exit 0
ruff format "$f" >/dev/null
out=$(ruff check "$f" 2>&1) || { echo "$out" >&2; exit 2; }
