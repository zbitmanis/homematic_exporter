# Review rules

Python changes go through `python-reviewer` (`fastapi-reviewer` for `app/`), then `security-reviewer`. Review against `specs/spec.md`, `specs/plan.md` and `CLAUDE.md`. The author agent cannot approve its own change.

## Passes
1. **Correctness:** matches spec; poll loop survives errors; scrapes never hit the source.
2. **Security:** no token/PIN in logs, metrics or `/status`; state perms 0700/0600; `yaml.safe_load` only, no blocking I/O in async code; debug routes off by default.
3. **Compliance:** metric naming and units; label cardinality; meta-metrics present; SBOM updated if dependencies changed.
4. **Boundaries:** change touches only the owning module; `contracts.py` changes have a spec change.

## Severity
- **Important (blocks merge):** any pass failure above, weakened or deleted tests, new dependency without SBOM entry.
- **Nit:** style and naming. At most five per review.

## Skip
Generated files, `docs/sbom/sbom.cdx.json`, recorded test fixtures.
