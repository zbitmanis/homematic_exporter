"""Module ownership guardrails (spec 12.1): library, CI check script, worktree helper, hook."""

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
HELPER = SCRIPTS / "new_module_worktree.sh"
OUTSIDE = Path("/nonexistent-hmx-outside")  # never created; not under any temp dir or $HOME


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lib = _load("ownership_lib", SCRIPTS / "ownership_lib.py")
CONFIG: dict[str, Any] = lib.parse_simple_yaml(OWNERSHIP.read_text())
CONTRACT = "src/homematic_exporter/contracts.py"
STATE_FILE = "src/homematic_exporter/state/s.py"


# --- the restricted YAML parser ---------------------------------------------------------------


def test_real_file_parses_validates_and_matches_pyyaml() -> None:
    assert CONFIG == yaml.safe_load(OWNERSHIP.read_text())
    lib.validate_config(CONFIG)


@pytest.mark.parametrize(
    "text",
    [
        "a: 1\n",
        "a: true\nb: false\n",
        "a: 'x y'\n",
        'a: "x \\" y"\n',
        'a: "x\\" # c"\n',  # escaped quote, then a # inside the string
        "a: 'it''s'\n",
        "a: word-1.2/x_y\n",
        "a:\n  - 'x'\n  - \"y # z\"\n",
        "a: ['x', 'y,z', plain]\nb: []\n",
        "m:\n  k:\n    - 'z'\n  j: [a, b]\n",
        "# only a comment\na: 1 # trailing\n",
    ],
)
def test_parser_agrees_with_pyyaml_on_the_supported_subset(text: str) -> None:
    assert lib.parse_simple_yaml(text) == (yaml.safe_load(text) or {})


def test_parser_edge_cases() -> None:
    text = (
        "# c\nversion: 2\nlist:\n  - 'a'  # note\n  - \"b # c\"\n"
        "flow: [x, \"y,z\"]\nok: true\nm:\n  k:\n    - 'it''s'\n"
    )
    expected = {
        "version": 2,
        "list": ["a", "b # c"],
        "flow": ["x", "y,z"],
        "ok": True,
        "m": {"k": ["it's"]},
    }
    assert lib.parse_simple_yaml(text) == expected
    assert lib.parse_simple_yaml("") == {}


@pytest.mark.parametrize(
    "text",
    [
        "a:\n\t- x\n",  # tab indentation
        "a:\n  - 'unterminated\n",
        "a: [x, 'y]\n",
        "a:\n- x\n",  # list at the same indent as its key
        "a:\n  - k: v\n",  # mapping inside a list
        "a: 1\na: 2\n",  # duplicate key
        "- x\n- y\n",  # root is not a mapping
        "just text\n",
        "a: 'x' trailing\n",
        "a:\n  b: 1\n   c: 2\n",  # unexpected indentation
        "a: it's # c\n",  # apostrophe in a plain scalar
        'a: "x\\ny"\n',  # unsupported escape
        "a: yes\n",
        "a: no\n",
        "a: on\n",
        "a: NULL\n",
        "a: ~\n",
        "a: True\n",
        "a: -1\n",
        "a: +1\n",
        "a: 1.5\n",
        "a: 0x1F\n",
        "a: 1_000\n",
        "a: '\u0661\u0662'x\n",
        "a: \u0661\u0662\n",  # Unicode digits are not integers
        "a: {b: 1}\n",
        "a: !!str x\n",
        "a: &x y\n",
        "a: *x\n",
        "a: @x\n",
        "a: - x\n",
        "a: -\n",
        "a: [[1], 2]\n",
        "a: [x]]\n",
        "a: [x,,y]\n",
        "a: [x,]\n",
        '"a b": 1\n',  # quoted key
        "a b: 1\n",  # key with a space
    ],
)
def test_parser_rejects_what_it_does_not_understand(text: str) -> None:
    with pytest.raises(ValueError):
        lib.parse_simple_yaml(text)


@pytest.mark.parametrize(
    "bad",
    [
        {"module": {"state": ["a/**"]}},  # misspelled key
        {"modules": {"state": ["a/**"]}, "contract_file": ["x"]},  # misspelled key
        {"modules": {}},
        {"modules": {"state": ["a/**"]}, "editable_sections": {"f.yaml": "metrics"}},
        {"modules": {"state": ["tests/state/"]}},
        {"contract_files": ["a**b"]},
        {"modules": {"s": [""]}},
    ],
)
def test_validate_config_rejects_rules_that_never_match(bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        lib.validate_config(bad)


# --- globs and branches -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("glob", "path", "expected"),
    [
        ("src/x/state/**", "src/x/state/a.py", True),
        ("src/x/state/**", "src/x/state/sub/dir/b.py", True),
        ("src/x/state/**", "src/x/state", False),
        ("src/x/state/**", "src/x/statex/a.py", False),
        ("**/conftest.py", "tests/state/conftest.py", True),
        ("**/conftest.py", "conftest.py", True),
        ("src/**/a.py", "src/x/y/a.py", True),
        ("src/**/a.py", "src/a.py", True),
        ("config/default-config.yaml", "config/default-config.yaml", True),
        ("config/default-config.yaml", "config/default-config.yaml.bak", False),
        ("a.b+c", "a.b+c", True),
        ("a.b+c", "aXb+c", False),
        ("*.md", "a.md", True),
        ("*.md", "dir/a.md", False),
        ("?.md", "a.md", True),
        ("?.md", "ab.md", False),
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


@pytest.mark.parametrize(
    "branch",
    [
        "feat/state2",
        "feat/State",
        "feat/state_x",
        "fix/app.x",
        "feat/metrics_v2",
        "feat/application",
    ],
)
def test_lookalike_module_branches_fail_closed(branch: str) -> None:
    problems = lib.check_changes(CONFIG, branch, ["README.md"])
    assert any("looks like a module branch" in p for p in problems)


@pytest.mark.parametrize(
    "branch", ["docs/x", "chore/state", "Feat/state", "state", "main", "hotfix/a"]
)
def test_branches_must_use_the_owners_scheme(branch: str) -> None:
    assert any("must start with" in p for p in lib.check_changes(CONFIG, branch, ["README.md"]))


@pytest.mark.parametrize(
    "branch",
    [
        "feat/ownership-guard",
        "feat/contracts",
        "feat/spec",
        "fix/phase-2-readiness",
        "feat/closing-review-task",
    ],
)
def test_the_owners_existing_coordinator_branches_pass(branch: str) -> None:
    assert lib.check_changes(CONFIG, branch, ["pyproject.toml", "CLAUDE.md"]) == []


# --- change rules -------------------------------------------------------------------------------


def test_module_branch_inside_its_paths_is_ok() -> None:
    changed = [STATE_FILE, "tests/state/test_store.py", "specs/plans/state.md"]
    assert lib.check_changes(CONFIG, "feat/state", changed) == []


def test_module_branch_outside_its_paths_is_flagged() -> None:
    problems = lib.check_changes(
        CONFIG, "feat/state", [STATE_FILE, "pyproject.toml", "src/homematic_exporter/source/x.py"]
    )
    assert len(problems) == 1 and "pyproject.toml" in problems[0] and "source/x.py" in problems[0]


def test_module_cannot_edit_shared_fixture_or_ownership_file() -> None:
    for path in (
        "tests/fixtures/mini_state.json",
        "tests/conftest.py",
        ".claude/ownership.yaml",
        "specs/spec.md",
    ):
        assert lib.check_changes(CONFIG, "feat/source", [path])


def test_contract_change_needs_the_spec_but_may_touch_module_code() -> None:
    assert (
        lib.check_changes(
            CONFIG, "fix/contracts-x", [CONTRACT, "specs/spec.md", "tests/test_contracts.py"]
        )
        == []
    )
    assert any(
        "specs/spec.md" in p for p in lib.check_changes(CONFIG, "fix/contracts-x", [CONTRACT])
    )
    breaking = [CONTRACT, "specs/spec.md", "src/homematic_exporter/app/a.py"]
    assert (
        lib.check_changes(CONFIG, "fix/contracts-x", breaking) == []
    )  # no deadlock for breaking changes
    assert any("also changes module code" in w for w in lib.warnings_for(CONFIG, breaking))
    assert lib.warnings_for(CONFIG, [CONTRACT, "specs/spec.md"]) == []


def test_sections_outside() -> None:
    base = {"extract": {"a": 1}, "tuning": {"b": 2}, "metrics": []}
    assert lib.sections_outside(base, {**base, "metrics": [{"n": 1}]}, ["metrics"]) == []
    assert lib.sections_outside(base, {**base, "tuning": {"b": 3}}, ["metrics"]) == ["tuning"]
    assert lib.sections_outside(base, {**base, "newkey": 1}, ["metrics"]) == ["newkey"]
    assert lib.sections_outside(base, {"metrics": []}, ["metrics"]) == ["extract", "tuning"]


def test_hook_decisions() -> None:
    decision, message = lib.hook_decision(CONFIG, "state", CONTRACT)
    assert decision == "block" and "Requests" in message and "specs/plans/state.md" in message
    assert lib.hook_decision(CONFIG, "state", STATE_FILE)[0] == "allow"
    assert lib.hook_decision(CONFIG, "nope", "x")[0] == "block"
    assert lib.hook_decision(CONFIG, None, "pyproject.toml")[0] == "allow"
    assert lib.hook_decision(CONFIG, None, CONTRACT)[0] == "warn"


# --- real git repository: CI script, helper script and hook as subprocesses -------------------

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
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    shutil.copy(OWNERSHIP, tmp_path / ".claude" / "ownership.yaml")
    shutil.copy(HOOK, tmp_path / ".claude" / "hooks" / "path_guard.py")
    shutil.copy(SCRIPTS / "ownership_lib.py", tmp_path / "scripts" / "ownership_lib.py")
    shutil.copy(HELPER, tmp_path / "scripts" / "new_module_worktree.sh")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "default-config.yaml").write_text(
        "version: 1\ntuning:\n  a: 1\nextract:\n  b: 2\nmetrics: []\n"
    )
    for rel in (CONTRACT, "tests/conftest.py", "specs/spec.md", "pyproject.toml"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("# base\n")
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


def run_check(repo: Path, branch: str, base: str = "main") -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPTS / "check_ownership.py"), "--repo", str(repo)]
    return subprocess.run(
        [*cmd, "--base", base, "--branch", branch], capture_output=True, text=True
    )


def test_ci_script_passes_inside_the_module_and_fails_outside(repo: Path) -> None:
    commit_files(repo, "feat/state", {STATE_FILE: "a = 1\n"})
    ok = run_check(repo, "feat/state")
    assert ok.returncode == 0 and "ownership ok" in ok.stdout
    git(repo, "checkout", "-q", "main")
    commit_files(repo, "feat/state-b", {"pyproject.toml": "x = 2\n"})
    bad = run_check(repo, "feat/state-b")
    assert bad.returncode == 1 and "pyproject.toml" in bad.stderr


def test_ci_script_sees_both_sides_of_a_rename(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feat/state")
    (repo / "src" / "homematic_exporter" / "state").mkdir(parents=True)
    git(repo, "mv", "tests/conftest.py", "tests/state_conftest_moved.py")  # outside the module
    git(repo, "mv", CONTRACT, "src/homematic_exporter/state/contracts.py")  # allowed destination!
    git(repo, "commit", "-q", "-m", "moves")
    result = run_check(repo, "feat/state")
    assert result.returncode == 1
    assert "tests/conftest.py" in result.stderr and CONTRACT in result.stderr


def test_ci_script_reads_the_rules_from_the_base_not_the_pr(repo: Path) -> None:
    text = (repo / ".claude" / "ownership.yaml").read_text()
    loosened = text.replace(
        '    - "specs/plans/state.md"\n', '    - "specs/plans/state.md"\n    - "pyproject.toml"\n'
    )
    commit_files(
        repo, "feat/state", {".claude/ownership.yaml": loosened, "pyproject.toml": "x = 3\n"}
    )
    assert run_check(repo, "feat/state").returncode == 1


def test_ci_script_fails_on_an_unresolvable_base_and_skips_a_bootstrap_base(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    commit_files(repo, "feat/state", {STATE_FILE: "a = 1\n"})
    bad = run_check(repo, "feat/state", base="origin/nonexistent")
    assert bad.returncode == 1 and "does not resolve" in bad.stderr
    boot = tmp_path_factory.mktemp("bootstrap")
    git(boot, "init", "-q", "-b", "main")
    (boot / "a.txt").write_text("a\n")
    git(boot, "add", "-A")
    git(boot, "commit", "-q", "-m", "base")
    commit_files(boot, "feat/state", {"pyproject.toml": "x\n"})
    skipped = run_check(boot, "feat/state")
    assert skipped.returncode == 0 and "bootstrap" in skipped.stdout


def test_ci_script_enforces_branch_scheme_and_lookalikes(repo: Path) -> None:
    commit_files(repo, "chore/state", {"README.md": "x\n"})
    assert run_check(repo, "chore/state").returncode == 1
    git(repo, "checkout", "-q", "main")
    commit_files(repo, "feat/state2", {"README.md": "x\n"})
    assert run_check(repo, "feat/state2").returncode == 1
    git(repo, "checkout", "-q", "main")
    commit_files(repo, "feat/ownership-guard", {"pyproject.toml": "y\n"})
    assert run_check(repo, "feat/ownership-guard").returncode == 0


def test_ci_script_prints_a_warning_for_a_breaking_contract_change(repo: Path) -> None:
    commit_files(
        repo,
        "fix/contracts-x",
        {CONTRACT: "# c\n", "specs/spec.md": "# s\n", "src/homematic_exporter/app/a.py": "x\n"},
    )
    result = run_check(repo, "fix/contracts-x")
    assert result.returncode == 0 and "warning: contract change" in result.stdout


CONFIG_SAME = "version: 1\ntuning:\n  a: 1\nextract:\n  b: 2\n"


def test_metrics_may_change_only_its_list(repo: Path) -> None:
    commit_files(
        repo,
        "feat/metrics",
        {"config/default-config.yaml": CONFIG_SAME + "metrics:\n  - name: x\n"},
    )
    assert run_check(repo, "feat/metrics").returncode == 0
    for branch, text in (
        ("fix/metrics-tuning", "version: 1\ntuning:\n  a: 9\nextract:\n  b: 2\nmetrics: []\n"),
        ("fix/metrics-newkey", CONFIG_SAME + "metrics: []\nextra: 1\n"),
    ):
        git(repo, "checkout", "-q", "main")
        commit_files(repo, branch, {"config/default-config.yaml": text})
        assert run_check(repo, branch).returncode == 1, branch
    git(repo, "checkout", "-q", "main")
    git(repo, "checkout", "-q", "-b", "fix/metrics-delete")
    git(repo, "rm", "-q", "config/default-config.yaml")
    git(repo, "commit", "-q", "-m", "rm")
    assert run_check(repo, "fix/metrics-delete").returncode == 1


def test_helper_script_validates_its_arguments(repo: Path) -> None:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "scripts/new_module_worktree.sh", *args],
            cwd=repo,
            capture_output=True,
            text=True,
        )

    assert run("bogus").returncode == 2
    wrong_branch = run("state", "feat/source")
    assert wrong_branch.returncode == 2 and "feat/state" in wrong_branch.stderr
    assert run().returncode != 0


# --- the hook ------------------------------------------------------------------------------------


def run_hook(
    repo: Path, file_path: Path | str, cwd: Path | str | None = None
) -> subprocess.CompletedProcess[str]:
    payload = {
        "tool_name": "Edit",
        "cwd": str(cwd or repo),
        "tool_input": {"file_path": str(file_path)},
    }
    hook = repo / ".claude" / "hooks" / "path_guard.py"
    return subprocess.run(
        [sys.executable, str(hook)], input=json.dumps(payload), capture_output=True, text=True
    )


def mark(repo: Path, module: str = "state") -> None:
    (repo / ".hmx-module").write_text(module + "\n")


def test_hook_blocks_a_module_agent_outside_its_module(repo: Path) -> None:
    mark(repo)
    blocked = run_hook(repo, repo / "pyproject.toml")
    assert blocked.returncode == 2 and "Requests" in blocked.stderr
    for forbidden in (
        CONTRACT,
        ".hmx-module",
        ".claude/ownership.yaml",
        ".claude/settings.json",
        ".claude/hooks/path_guard.py",
    ):
        assert run_hook(repo, repo / forbidden).returncode == 2, forbidden
    assert run_hook(repo, repo / STATE_FILE).returncode == 0


def test_hook_resolves_relative_paths_against_the_payload_cwd(repo: Path) -> None:
    mark(repo)
    state_dir = repo / "src" / "homematic_exporter" / "state"
    assert run_hook(repo, "new.py", cwd=state_dir).returncode == 0
    assert run_hook(repo, "../contracts.py", cwd=state_dir).returncode == 2
    assert run_hook(repo, repo / STATE_FILE, cwd="/").returncode == 0  # cwd does not pick the root


def test_hook_blocks_edits_outside_the_worktree_but_allows_temp_files(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    mark(repo)
    outside = run_hook(repo, OUTSIDE / "src" / "homematic_exporter" / "contracts.py")
    assert outside.returncode == 2 and "outside your worktree" in outside.stderr
    scratch = tmp_path_factory.mktemp("scratch") / "notes.txt"
    assert run_hook(repo, scratch).returncode == 0


def test_hook_blocks_a_sibling_worktree_even_when_it_lives_in_temp(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    mark(repo)
    sibling = tmp_path_factory.mktemp("sibling")
    (sibling / ".claude").mkdir()
    (sibling / ".claude" / "ownership.yaml").write_text("version: 1\n")
    result = run_hook(repo, sibling / "src" / "x.py")
    assert result.returncode == 2 and "outside your worktree" in result.stderr
    link = repo / "tests" / "state" / "to_sibling"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(sibling)
    assert run_hook(repo, link / "x.py").returncode == 2


def test_hook_blocks_a_symlink_that_escapes_the_worktree(repo: Path) -> None:
    mark(repo)
    link = repo / "tests" / "state" / "lnk"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(OUTSIDE)
    assert run_hook(repo, link / "x.py").returncode == 2
    inside = repo / "tests" / "state" / "inside"
    inside.symlink_to(repo / "pyproject.toml")
    assert run_hook(repo, inside).returncode == 2  # points at a forbidden path inside the repo


@pytest.mark.skipif(
    not os.path.exists(str(Path(__file__)).swapcase()), reason="case-sensitive file system"
)
def test_hook_handles_case_insensitive_paths(repo: Path) -> None:
    mark(repo)
    variant = str(repo / CONTRACT).replace("homematic_exporter", "Homematic_Exporter")
    assert run_hook(repo, variant).returncode == 2


def test_hook_fails_closed_for_a_module_agent_and_open_for_the_coordinator(repo: Path) -> None:
    (repo / ".claude" / "ownership.yaml").write_text("modules:\n\t- broken\n")
    open_ = run_hook(repo, repo / "pyproject.toml")
    assert open_.returncode == 0 and "allowed" in json.loads(open_.stdout)["systemMessage"]
    mark(repo)
    closed = run_hook(repo, repo / STATE_FILE)
    assert closed.returncode == 2 and "failing closed" in closed.stderr


def test_hook_blocks_an_unknown_module_marker(repo: Path) -> None:
    mark(repo, "typo")
    assert run_hook(repo, repo / "a.py").returncode == 2


def test_hook_only_warns_the_coordinator_about_contracts(repo: Path) -> None:
    warned = run_hook(repo, repo / CONTRACT)
    assert (
        warned.returncode == 0 and "shared contract" in json.loads(warned.stdout)["systemMessage"]
    )
    quiet = run_hook(repo, repo / "pyproject.toml")
    assert quiet.returncode == 0 and quiet.stdout.strip() == ""


def test_hook_ignores_calls_without_a_path_and_garbage_input(repo: Path) -> None:
    hook = repo / ".claude" / "hooks" / "path_guard.py"
    no_path = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps({"tool_input": {}}),
        capture_output=True,
        text=True,
    )
    assert no_path.returncode == 0
    garbage = subprocess.run(
        [sys.executable, str(hook)], input="not json", capture_output=True, text=True
    )
    assert garbage.returncode == 0 and "allowed" in json.loads(garbage.stdout)["systemMessage"]
