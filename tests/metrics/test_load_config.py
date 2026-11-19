"""`load_config` (spec R19, R21): resolution order, file hygiene, hostile YAML."""

import logging
import os
from pathlib import Path
from typing import Any

import pytest

from homematic_exporter.metrics import config as config_module
from homematic_exporter.metrics import load_config
from homematic_exporter.metrics.config import MAX_CONFIG_BYTES, ConfigError
from tests.metrics.conftest import metric


def test_explicit_path_is_loaded(raw_config: dict[str, Any], write_config: Any) -> None:
    raw_config["metrics"] = [metric()]
    config = load_config(write_config(raw_config))
    assert [m.name for m in config.metrics] == ["homematic_room_temperature_celsius"]


def test_explicit_path_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")


def test_explicit_path_does_not_fall_back_to_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write_config: Any
) -> None:
    monkeypatch.setattr(config_module, "MOUNT_CONFIG_PATH", write_config({"version": 1}, "m.yaml"))
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.yaml")


def test_mount_path_wins_over_the_bundled_default(
    raw_config: dict[str, Any],
    write_config: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_config["metrics"] = [metric(name="homematic_room_mounted_celsius")]
    mount = write_config(raw_config, "mount.yaml")
    monkeypatch.setattr(config_module, "MOUNT_CONFIG_PATH", mount)
    with caplog.at_level(logging.INFO, logger=config_module.__name__):
        config = load_config(None)
    assert config.metrics[0].name == "homematic_room_mounted_celsius"
    assert str(mount) in caplog.text


def test_bundled_default_is_used_when_nothing_is_mounted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(config_module, "MOUNT_CONFIG_PATH", tmp_path / "absent.yaml")
    with caplog.at_level(logging.INFO, logger=config_module.__name__):
        config = load_config()
    assert len(config.metrics) > 10
    assert "bundled default" in caplog.text


def test_broken_mount_fails_instead_of_falling_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write_config: Any
) -> None:
    monkeypatch.setattr(config_module, "MOUNT_CONFIG_PATH", write_config("version: [", "m.yaml"))
    with pytest.raises(ConfigError):
        load_config(None)


def test_environment_is_never_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw_config: dict[str, Any], write_config: Any
) -> None:
    monkeypatch.setenv("CONFIG_FILE", str(tmp_path / "from-env.yaml"))
    monkeypatch.setattr(config_module, "MOUNT_CONFIG_PATH", tmp_path / "absent.yaml")
    assert load_config(None).metrics
    assert load_config(write_config(raw_config)).metrics == ()


def test_symlinked_file_is_followed(raw_config: dict[str, Any], tmp_path: Path) -> None:
    # Kubernetes ConfigMap mounts are symlinks into a data directory.
    import yaml

    real = tmp_path / "real.yaml"
    real.write_text(yaml.safe_dump(raw_config))
    link = tmp_path / "link.yaml"
    link.symlink_to(real)
    assert load_config(link).metrics == ()


def test_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="regular file"):
        load_config(tmp_path)


def test_fifo_is_rejected_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "fifo.yaml"
    os.mkfifo(fifo)
    with pytest.raises(ConfigError, match="regular file"):
        load_config(fifo)


def test_oversized_file_is_rejected(write_config: Any) -> None:
    with pytest.raises(ConfigError, match="too large"):
        load_config(write_config("# " + "x" * MAX_CONFIG_BYTES))


def test_non_utf8_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_bytes(b"version: \xff\xfe\n")
    with pytest.raises(ConfigError, match="UTF-8"):
        load_config(path)


@pytest.mark.parametrize("text", ["", "# only a comment\n", "null\n", "- a\n- b\n", "just text\n"])
def test_non_mapping_documents_are_rejected(write_config: Any, text: str) -> None:
    with pytest.raises(ConfigError, match="mapping"):
        load_config(write_config(text))


def test_yaml_syntax_error_reports_line_not_content(write_config: Any) -> None:
    with pytest.raises(ConfigError) as info:
        load_config(write_config("version: 1\nmetrics: [\nsecret_token: hunter2hunter2\n  - :\n"))
    assert "line" in str(info.value)
    assert "hunter2" not in str(info.value)


def test_duplicate_keys_are_rejected(write_config: Any) -> None:
    with pytest.raises(ConfigError, match="line 3: duplicate key 'version'"):
        load_config(write_config("# c\nversion: 1\nversion: 1\n"))


def test_aliases_are_rejected(write_config: Any) -> None:
    text = "version: 1\nx: &a [1, 2]\ny: *a\n"
    with pytest.raises(ConfigError, match="aliases"):
        load_config(write_config(text))


def test_alias_bomb_is_rejected_quickly(write_config: Any) -> None:
    lines = ["a0: &a0 [x, x, x, x, x, x, x, x, x]"]
    lines += [f"a{i}: &a{i} [*a{i - 1}, *a{i - 1}, *a{i - 1}, *a{i - 1}]" for i in range(1, 12)]
    with pytest.raises(ConfigError, match="aliases"):
        load_config(write_config("\n".join(lines) + "\n"))


def test_python_tags_are_rejected(write_config: Any) -> None:
    with pytest.raises(ConfigError):
        load_config(write_config("version: !!python/object/apply:os.system ['true']\n"))


def test_deep_nesting_is_a_config_error_not_a_crash(write_config: Any) -> None:
    with pytest.raises(ConfigError, match="nest"):
        load_config(write_config("a: " + "[" * 5000 + "]" * 5000 + "\n"))


def test_non_string_keys_are_rejected(raw_config: dict[str, Any], write_config: Any) -> None:
    raw_config[1] = "x"
    with pytest.raises(ConfigError, match=r"\[1\]"):
        load_config(write_config(raw_config))


def test_non_finite_yaml_numbers_are_rejected(
    raw_config: dict[str, Any], write_config: Any
) -> None:
    text = write_config(raw_config).read_text().replace("heat_demand_min_position: 0.0", "heat_demand_min_position: .nan")
    with pytest.raises(ConfigError, match="tuning.heat_demand_min_position"):
        load_config(write_config(text, "nan.yaml"))


def test_error_message_names_the_file(raw_config: dict[str, Any], write_config: Any) -> None:
    raw_config["metrics"] = [metric(labels=["sgtin"])]
    path = write_config(raw_config)
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert str(path) in str(info.value)
    assert "metrics[0].labels[0]: unknown label 'sgtin'" in str(info.value)


def test_default_config_file_is_valid() -> None:
    config = load_config(Path(__file__).parents[2] / "config" / "default-config.yaml")
    assert config.tuning.state_retention_days == 90
