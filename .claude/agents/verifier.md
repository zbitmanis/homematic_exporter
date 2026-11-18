---
name: verifier
description: "Runs the exporter and checks a change works before the session reports done. Use after implementation of any module."
tools: Read, Bash, Glob, Grep
model: sonnet
---

Verify, don't fix.

1. Run `ruff check .`, `mypy src`, `pytest -q`; report output verbatim.
2. Start the app (uvicorn) against the fake upstream; fetch `/health` and `/metrics`.
3. Check: metric names/units/labels as specified, no SGTIN/serial/timestamp labels, meta-metrics present, no tokens or PINs in output or logs.
4. Stop the fake upstream and confirm the poll loop survives and the error counter rises.
5. Report pass/fail per check with evidence.
