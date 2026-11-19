"""Fix round 2: readable errors, message redaction, mount edge cases, bidi marks."""

from pathlib import Path
from typing import Any

import pytest

from homematic_exporter.metrics import ConfigError, load_config, parse_config
from homematic_exporter.metrics import config as config_module
from homematic_exporter.metrics.schema import quote
from homematic_exporter.metrics.text import clean_text
from tests.metrics.conftest import metric


def message(raw: dict[str, Any]) -> str:
    with pytest.raises(ConfigError) as info:
        parse_config(raw)
    return str(info.value)


def test_duplicate_numbered_metric_name_stays_readable(raw_config: dict[str, Any]) -> None:
    name = "homematic_room_temperature_celsius_2"
    raw_config["metrics"] = [metric(name=name), metric(name=name)]
    msg = message(raw_config)
    assert f"'{name}'" in msg
    assert "REDACTED" not in msg


def test_long_unknown_key_with_letters_and_digits_is_redacted(raw_config: dict[str, Any]) -> None:
    key = "abcdef0123456789abcdef0123456789zzabcdef"
    raw_config[key] = 1
    msg = message(raw_config)
    assert key not in msg
    assert "unknown key" in msg


def test_messages_from_config_models_do_not_echo_raw_keys(raw_config: dict[str, Any]) -> None:
    raw_config["extract"]["rooms"]["abcdef0123456789abcdef0123456789zz"] = "x"
    raw_config["extract"]["device_flags"]["p4ssw0rd=hunter2"] = "x"
    msg = message(raw_config)
    assert "abcdef0123456789abcdef0123456789zz" not in msg
    assert "hunter2" not in msg
    assert "extract.rooms" in msg
    assert "extract.device_flags" in msg


def test_unknown_label_names_stay_readable(raw_config: dict[str, Any]) -> None:
    raw_config["metrics"] = [metric(labels=["sgtin"])]
    assert "unknown label 'sgtin'" in message(raw_config)


def test_yaml_parse_cost_comment_is_honest() -> None:
    text = Path(config_module.__file__).read_text()
    assert "about 0.5 s" not in text


def test_dangling_link_says_broken_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    link = tmp_path / "config.yaml"
    link.symlink_to(tmp_path / "gone.yaml")
    monkeypatch.setattr(config_module, "MOUNT_CONFIG_PATH", link)
    with pytest.raises(ConfigError, match="broken link"):
        load_config(None)


def test_file_where_the_mount_directory_should_be_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "config-dir"
    blocker.write_text("not a directory")
    monkeypatch.setattr(config_module, "MOUNT_CONFIG_PATH", blocker / "config.yaml")
    with pytest.raises(ConfigError):
        load_config(None)


@pytest.mark.parametrize("mark", ["‎", "‏", "؜"])
def test_directional_marks_are_replaced(mark: str) -> None:
    assert clean_text(f"a{mark}b") == "a b"


def test_zwj_and_zwnj_survive() -> None:
    assert clean_text("a‍b‌c") == "a‍b‌c"


def test_cut_never_leaves_trailing_space() -> None:
    text = "x" * 199 + " " + "y" * 50
    out = clean_text(text)
    assert out == "x" * 199
    assert clean_text("   " + "z" * 300) == "z" * 200


def test_cut_values_keep_their_closing_quote() -> None:
    out = quote("a" * 100)
    assert out.endswith("...'")
    assert out.startswith("'a")
    assert quote("short") == "'short'"
