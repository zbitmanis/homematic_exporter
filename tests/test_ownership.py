"""Module ownership guardrails (spec 12.1): library, CI check script and Claude Code hook."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "scripts"
HOOK = ROOT / ".claude" / "hooks" / "path_guard.py"
OWNERSHIP = ROOT / ".claude" / "ownership.yaml"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lib = _load("ownership_lib", SCRIPTS / "ownership_lib.py")
CONFIG: dict[str, Any] = lib.parse_simple_yaml(OWNERSHIP.read_text())


def test_simple_yaml_parser_matches_pyyaml_on_the_real_file() -> None:
    assert CONFIG == yaml.safe_load(OWNERSHIP.read_text())


def test_simple_yaml_parser_edge_cases() -> None:
    parsed = lib.parse_simple_yaml(
        "# c\nversion: 2\nlist:\n  - 'a'\n  - \"b c\"\nflow: [x, y]\nm:\n  k:\n    - z\n"
    )
    assert parsed == {"version": 2, "list": ["a", "b c"], "flow": ["x", "y"], "m": {"k": ["z"]}}
    assert lib.parse_simple_yaml("") == {}


@pytest.mark.parametrize(
    ("glob", "path", "expected"),
    [
        ("src/x/state/**", "src/x/state/a.py", True),
        ("src/x/state/**", "src/x/state/sub/dir/b.py", True),
        ("src/x/state/**", "src/x/state", False),
        ("src/x/state/**", "src/x/statex/a.py", False),
        ("tests/state/**", "tests/state/test_a.py", True),
        ("config/default-config.yaml", "config/default-config.yaml", True),
        ("config/default-config.yaml", "config/default-config.yaml.bak", False),
        ("*.md", "a.md", True),
        ("*.md", "dir/a.md", False),
        ("**/*.md", "dir/sub/a.md", True),
    ],
)
def test_glob_matching(glob: str, path: str, expected: bool) -> None:
    assert lib.matches(path, [glob]) is expected


@pytest.mark.parametrize(
    ("branch", "expected"),
    [
        ("feat/state", "state"),
        ("fix/metrics", "metrics"),
        ("feat/source-parser", "source"),
        ("fix/app/startup", "app"),
        ("feat/application", None),
        ("feat/stately", None),
        ("feat/ownership-guard", None),
        ("docs/state", None),
        ("main", None),
    ],
)
def test_branch_to_module(branch: str, expected: str | None) -> None:
    assert lib.module_for_branch(branch, CONFIG["modules"]) == expected


def test_module_branch_inside_its_paths_is_ok() -> None:
    changed = [
        "src/homematic_exporter/state/store.py",
        "tests/state/test_store.py",
        "specs/plans/state.md",
    ]
    assert lib.check_changes(CONFIG, "feat/state", changed) == []


def test_module_branch_outside_its_paths_is_flagged() -> None:
    changed = [
        "src/homematic_exporter/state/store.py",
        "pyproject.toml",
        "src/homematic_exporter/source/x.py",
    ]
    problems = lib.check_changes(CONFIG, "feat/state", changed)
    assert len(problems) == 1
    assert "pyproject.toml" in problems[0] and "source/x.py" in problems[0]
    assert "specs/plans/state.md" in problems[0]


def test_module_cannot_edit_shared_fixture_or_ownership_file() -> None:
    for path in ("tests/fixtures/mini_state.json", "tests/conftest.py", ".claude/ownership.yaml"):
        assert lib.check_changes(CONFIG, "feat/source", [path])


def test_coordinator_branch_is_unrestricted_except_the_contract_rule() -> None:
    assert lib.check_changes(CONFIG, "docs/anything", ["pyproject.toml", "CLAUDE.md"]) == []


def test_contract_change_needs_the_spec_and_no_module_code() -> None:
    contract = "src/homematic_exporter/contracts.py"
    assert (
        lib.check_changes(
            CONFIG, "fix/contracts-x", [contract, "specs/spec.md", "tests/test_contracts.py"]
        )
        == []
    )
    needs_spec = lib.check_changes(CONFIG, "fix/contracts-x", [contract])
    assert any("specs/spec.md" in p for p in needs_spec)
    mixed = lib.check_changes(
        CONFIG, "fix/contracts-x", [contract, "specs/spec.md", "src/homematic_exporter/app/a.py"]
    )
    assert any("own small PR" in p for p in mixed)


def test_sections_changed() -> None:
    base = {"extract": {"a": 1}, "tuning": {"b": 2}, "metrics": []}
    assert lib.sections_changed(base, {**base, "metrics": [{"n": 1}]}, ["extract", "tuning"]) == []
    assert lib.sections_changed(base, {**base, "tuning": {"b": 3}}, ["extract", "tuning"]) == [
        "tuning"
    ]


# --- hook decisions -------------------------------------------------------------------------


def test_hook_decisions() -> None:
    contract = "src/homematic_exporter/contracts.py"
    assert lib.hook_decision(CONFIG, "state", "src/homematic_exporter/state/a.py")[0] == "allow"
    decision, message = lib.hook_decision(CONFIG, "state", contract)
    assert decision == "block" and "Requests" in message and "specs/plans/state.md" in message
    assert lib.hook_decision(CONFIG, "nope", "x")[0] == "block"
    assert lib.hook_decision(CONFIG, None, "pyproject.toml")[0] == "allow"
    assert lib.hook_decision(CONFIG, None, contract)[0] == "warn"


# --- real git repo: CI script and hook as subprocesses ---------------------------------------

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}  # fmt: skip


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    done = subprocess.run(
        ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True
    )
    return done.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / ".claude").mkdir()
    shutil.copy(OWNERSHIP, tmp_path / ".claude" / "ownership.yaml")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "default-config.yaml").write_text(
        "version: 1\ntuning:\n  a: 1\nextract:\n  b: 2\nmetrics: []\n"
    )
    (tmp_path / "pyproject.toml").write_text("x = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def commit_files(repo: Path, branch: str, files: dict[str, str]) -> None:
    git(repo, "checkout", "-q", "-b", branch)
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")


def run_check(repo: Path, branch: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPTS / "check_ownership.py"), "--repo", str(repo)]
    return subprocess.run(
        [*cmd, "--base", "main", "--branch", branch], capture_output=True, text=True
    )


def test_ci_script_passes_for_a_module_inside_its_paths(repo: Path) -> None:
    commit_files(repo, "feat/state", {"src/homematic_exporter/state/s.py": "a = 1\n"})
    result = run_check(repo, "feat/state")
    assert result.returncode == 0 and "ownership ok" in result.stdout


def test_ci_script_fails_outside_the_module(repo: Path) -> None:
    commit_files(repo, "feat/state", {"pyproject.toml": "x = 2\n"})
    result = run_check(repo, "feat/state")
    assert result.returncode == 1 and "pyproject.toml" in result.stderr


def test_ci_script_reads_the_rules_from_the_base_not_the_pr(repo: Path) -> None:
    loosened = (
        (repo / ".claude" / "ownership.yaml")
        .read_text()
        .replace(
            '    - "specs/plans/state.md"\n',
            '    - "specs/plans/state.md"\n    - "pyproject.toml"\n',
        )
    )
    commit_files(
        repo, "feat/state", {".claude/ownership.yaml": loosened, "pyproject.toml": "x = 3\n"}
    )
    assert run_check(repo, "feat/state").returncode == 1


def test_metrics_may_change_its_list_but_not_extract_or_tuning(repo: Path) -> None:
    ok = "version: 1\ntuning:\n  a: 1\nextract:\n  b: 2\nmetrics:\n  - name: x\n"
    commit_files(repo, "feat/metrics", {"config/default-config.yaml": ok})
    assert run_check(repo, "feat/metrics").returncode == 0
    git(repo, "checkout", "-q", "main")
    bad = "version: 1\ntuning:\n  a: 9\nextract:\n  b: 2\nmetrics: []\n"
    commit_files(repo, "fix/metrics-tuning", {"config/default-config.yaml": bad})
    result = run_check(repo, "fix/metrics-tuning")
    assert result.returncode == 1 and "tuning" in result.stderr


def test_ci_script_skips_when_the_base_has_no_ownership_file(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("a\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    commit_files(tmp_path, "feat/state", {"pyproject.toml": "x\n"})
    result = run_check(tmp_path, "feat/state")
    assert result.returncode == 0 and "skipped" in result.stdout


def run_hook(
    repo: Path, file_path: Path | str, payload_extra: dict[str, Any] | None = None
) -> subprocess.CompletedProcess[str]:
    payload = {"tool_name": "Edit", "cwd": str(repo), "tool_input": {"file_path": str(file_path)}}
    payload.update(payload_extra or {})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True
    )


def test_hook_blocks_a_module_agent_outside_its_module(repo: Path) -> None:
    (repo / ".hmx-module").write_text("state\n")
    blocked = run_hook(repo, repo / "pyproject.toml")
    assert blocked.returncode == 2 and "Requests" in blocked.stderr
    contract = run_hook(repo, repo / "src" / "homematic_exporter" / "contracts.py")
    assert contract.returncode == 2
    assert run_hook(repo, repo / ".hmx-module").returncode == 2  # cannot rewrite its own marker
    assert run_hook(repo, repo / "src" / "homematic_exporter" / "state" / "new.py").returncode == 0


def test_hook_only_warns_the_coordinator_about_contracts(repo: Path) -> None:
    warned = run_hook(repo, repo / "src" / "homematic_exporter" / "redact.py")
    assert (
        warned.returncode == 0 and "shared contract" in json.loads(warned.stdout)["systemMessage"]
    )
    quiet = run_hook(repo, repo / "pyproject.toml")
    assert quiet.returncode == 0 and quiet.stdout.strip() == ""


def test_hook_ignores_paths_outside_the_repo_and_other_tools(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    (repo / ".hmx-module").write_text("state\n")
    outside = tmp_path_factory.mktemp("elsewhere") / "x.py"
    assert run_hook(repo, outside).returncode == 0
    no_path = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_input": {}}),
        capture_output=True,
        text=True,
    )
    assert no_path.returncode == 0


def test_hook_fails_open_on_garbage_input() -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK)], input="not json", capture_output=True, text=True
    )
    assert result.returncode == 0 and "allowed" in json.loads(result.stdout)["systemMessage"]


def test_hook_blocks_an_unknown_module_marker(repo: Path) -> None:
    (repo / ".hmx-module").write_text("typo\n")
    assert run_hook(repo, repo / "a.py").returncode == 2
