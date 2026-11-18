"""Module boundaries (docs/sbom/components.md).

Modules may share only contracts, config_models and redact.

`source`, `state` and `metrics` must not import each other or `app`. `app` and the top-level tool
modules (check_config, generate_config) may import everything.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent / "src" / "homematic_exporter"
MODULES = {"source", "state", "metrics", "app"}
SHARED = {"contracts", "config_models", "redact"}
UNRESTRICTED = {"app"}


def imported_modules(path: Path, package: str) -> set[str]:
    """Names of `homematic_exporter.<x>` top-level parts imported by one file."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        targets: list[str] = []
        if isinstance(node, ast.Import):
            targets = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                prefix = ".".join(parts[: len(parts) - (node.level - 1)])
                base = f"{prefix}.{base}".rstrip(".")
            targets = [base] + [f"{base}.{a.name}" for a in node.names]
        for t in targets:
            parts = t.split(".")
            if parts[0] == "homematic_exporter" and len(parts) > 1:
                found.add(parts[1])
    return found


def violations(root: Path) -> list[str]:
    bad: list[str] = []
    for module in sorted(MODULES - UNRESTRICTED):
        for path in sorted((root / module).rglob("*.py")):
            rel = path.relative_to(root.parent).with_suffix("")
            package = ".".join(rel.parts[:-1])
            for other in imported_modules(path, package):
                if other in MODULES and other != module:
                    bad.append(f"{path.relative_to(root)} imports homematic_exporter.{other}")
    return bad


def test_real_tree_has_no_cross_module_imports() -> None:
    assert violations(ROOT) == []


def test_checker_detects_violations(tmp_path: Path) -> None:
    pkg = tmp_path / "homematic_exporter"
    (pkg / "source").mkdir(parents=True)
    (pkg / "state").mkdir()
    (pkg / "source" / "a.py").write_text("from homematic_exporter.state import x\n")
    (pkg / "source" / "b.py").write_text("from ..state import y\n")
    (pkg / "source" / "c.py").write_text(
        "from homematic_exporter.contracts import Room\nimport os\n"
    )
    (pkg / "state" / "d.py").write_text("import homematic_exporter.metrics.registry\n")
    found = violations(pkg)
    assert any("source/a.py" in v for v in found)
    assert any("source/b.py" in v for v in found)
    assert any("state/d.py" in v for v in found)
    assert not any("source/c.py" in v for v in found)
