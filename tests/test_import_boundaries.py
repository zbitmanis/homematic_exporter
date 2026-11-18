"""Module boundaries (docs/sbom/components.md, spec 12.1).

Modules may share only contracts, config_models and redact.
- `source`, `state`, `metrics` must not import each other or `app`.
- `app` may import the others **only in `app/wiring.py`**; the rest of `app` uses its own ports.
- `tests/<module>/` may import only its own module (plus shared code); `tests/e2e/` and the
  top-level tests are unrestricted.
Top-level tool modules (check_config, generate_config) may import everything.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent / "src" / "homematic_exporter"
TESTS = Path(__file__).parent
MODULES = {"source", "state", "metrics", "app"}
WIRING = {"app/wiring.py"}


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


def violations(src_root: Path, tests_root: Path) -> list[str]:
    bad: list[str] = []
    for module in sorted(MODULES):
        for path in sorted((src_root / module).rglob("*.py")):
            rel = path.relative_to(src_root)
            if module == "app" and rel.as_posix() in WIRING:
                continue
            package = ".".join(path.relative_to(src_root.parent).with_suffix("").parts[:-1])
            for other in imported_modules(path, package):
                if other in MODULES and other != module:
                    bad.append(f"src/{rel} imports homematic_exporter.{other}")
        for path in sorted((tests_root / module).rglob("*.py")):
            package = ".".join(path.relative_to(tests_root.parent).with_suffix("").parts[:-1])
            for other in imported_modules(path, package):
                if other in MODULES and other != module:
                    bad.append(
                        f"tests/{path.relative_to(tests_root)} imports homematic_exporter.{other}"
                    )
    return bad


def test_real_tree_has_no_cross_module_imports() -> None:
    assert violations(ROOT, TESTS) == []


def test_checker_detects_violations(tmp_path: Path) -> None:
    src = tmp_path / "src" / "homematic_exporter"
    tests = tmp_path / "tests"
    for d in (src / "source", src / "state", src / "app", tests / "metrics", tests / "app"):
        d.mkdir(parents=True)
    (src / "source" / "a.py").write_text("from homematic_exporter.state import x\n")
    (src / "source" / "b.py").write_text("from ..state import y\n")
    (src / "source" / "c.py").write_text(
        "from homematic_exporter.contracts import Room\nimport os\n"
    )
    (src / "state" / "d.py").write_text("import homematic_exporter.metrics.registry\n")
    (src / "app" / "wiring.py").write_text("from homematic_exporter.source import CloudSource\n")
    (src / "app" / "main.py").write_text("from homematic_exporter.metrics import Registry\n")
    (tests / "metrics" / "test_x.py").write_text(
        "from homematic_exporter.source import parse_snapshot\n"
    )
    (tests / "app" / "test_y.py").write_text("from homematic_exporter.app import create_app\n")
    found = violations(src, tests)
    assert any("source/a.py" in v for v in found)
    assert any("source/b.py" in v for v in found)
    assert any("state/d.py" in v for v in found)
    assert any("app/main.py" in v for v in found)  # only wiring.py may import concrete modules
    assert any("metrics/test_x.py" in v for v in found)  # tests/<module> stay in their module
    assert not any("source/c.py" in v for v in found)
    assert not any("wiring.py" in v for v in found)
    assert not any("test_y.py" in v for v in found)
