# Third-party notices

This repository's own licence is not declared in this file. This file lists third-party material that was copied or adapted into the repository and the notices its licence requires.

## everything-claude-code (ECC)

Parts of the agent harness in `.claude/` were copied or adapted from **everything-claude-code ("ECC")**, an open-source collection of agents, rules and skills for AI coding tools.

- Author and copyright holder: Affaan Mustafa
- Licence: MIT
- Version used: 2.2.3, commit `3f14a103a8694e51c1df9a806217a6d0b5f7a6f7` (copied from a local clone whose `origin` is `github.com/zbitmanis/everything-claude-code`, a fork of the upstream project)
- Copied on: 2026-11-18

This project is **not affiliated with, endorsed by, or sponsored by** the ECC author or project. ECC names and marks belong to their owners.

### What came from ECC

| Path | Status |
|---|---|
| `.claude/rules/common/*`, `.claude/rules/python/*` | Copied **unmodified** |
| `.claude/skills/python-patterns/`, `python-testing/`, `fastapi-patterns/` | Copied **unmodified** |
| `.claude/agents/fastapi-reviewer.md`, `python-reviewer.md` | Copied, **lightly modified** (project-specific checks, tool commands, quoted description) |
| `.claude/agents/architect.md`, `chief-of-staff.md`, `code-reviewer.md`, `code-simplifier.md`, `doc-updater.md`, `e2e-runner.md`, `harness-optimizer.md`, `performance-optimizer.md`, `security-reviewer.md` | **Derived**: ECC files used as the starting point and substantially rewritten for this Python project (Node/JS content removed). Structure, section headings and some wording remain from ECC. |
| The "Prompt Defense Baseline" block at the top of each agent | Retained from ECC |

Not from ECC: `.claude/agents/implementer.md`, `verifier.md`, `python-build-resolver.md` (written for this project; `python-build-resolver` was modelled on the structure of ECC's `go-build-resolver`), `.claude/hooks/`, `.claude/settings.json`, and everything outside `.claude/`.

Files derived from ECC may reference other ECC skills or commands that are not included in this repository.

### Licence text (MIT), as required for copies and substantial portions

```
MIT License

Copyright (c) 2026 Affaan Mustafa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Disclaimer

The ECC-derived agents, rules and skills are provided "as is", without warranty. They are AI-assistant configuration, not tested security or compliance controls: review their output before relying on it. Modifications made in this repository are the responsibility of this repository's maintainers, not of the ECC author.

## Python dependencies

Runtime and development dependencies are not copied into this repository. Their versions and licences are tracked in `docs/sbom/components.md` and the generated `docs/sbom/sbom.cdx.json`. Note: `homematicip` is GPL-3.0-or-later (accepted for private use; see the SBOM licence decision).
