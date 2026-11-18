# .claude/

Agent harness for this repository (agents, rules, skills, hooks, settings). See `docs/harness.md` for the roster and model policy.

**Attribution:** much of this directory was copied or adapted from the MIT-licensed project *everything-claude-code* (Affaan Mustafa). Which files, how they were changed and the licence text are in [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) at the repository root. Keep that notice when copying these files elsewhere. This project is not affiliated with or endorsed by the ECC author.

**Ownership:** `ownership.yaml` lists the paths each module agent may edit. It is read by the `ownership` CI check and by `hooks/path_guard.py`, which blocks edits in module worktrees (marked by an untracked `.hmx-module`) and only warns the coordinator about shared contracts. Create worktrees with `scripts/new_module_worktree.sh`.
