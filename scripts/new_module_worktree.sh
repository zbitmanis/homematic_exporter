#!/usr/bin/env bash
# Create an isolated worktree + branch for one module agent and mark it with .hmx-module so the
# path-guard hook keeps the agent inside its module (spec 12.1).
#   scripts/new_module_worktree.sh <state|metrics|source|app> [branch]   (branch default feat/<module>)
set -euo pipefail
module="${1:?usage: new_module_worktree.sh <state|metrics|source|app> [branch]}"
case "$module" in state | metrics | source | app) ;; *)
  echo "unknown module '$module'" >&2
  exit 2
  ;;
esac
root="$(git rev-parse --show-toplevel)"
dir="$(dirname "$root")/$(basename "$root")-$module"
branch="${2:-feat/$module}"
case "$branch" in "feat/$module" | "feat/$module"[-/]* | "fix/$module" | "fix/$module"[-/]*) ;; *)
  echo "branch must be feat/$module or fix/$module (optionally followed by - or / and text)" >&2
  exit 2
  ;;
esac
git fetch origin main --quiet
git worktree add --no-track "$dir" -b "$branch" origin/main
printf '%s\n' "$module" >"$dir/.hmx-module"
cat <<MSG

Worktree:  $dir   (branch $branch, marker .hmx-module = $module)
Task prompt for the module agent:
  You own ONLY the '$module' module. Read CLAUDE.md, docs/sbom/components.md,
  src/homematic_exporter/$module/CLAUDE.md and specs/plans/$module.md, plus spec section 12.1.
  Tests first. Edit only the paths in .claude/ownership.yaml for '$module'. Anything else:
  write it under "Requests" in your plan and stop. Finish with the plan's closing review task.
MSG
