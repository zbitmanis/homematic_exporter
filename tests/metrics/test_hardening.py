"""Fix round 1: hostile text in labels/version/help, bounded config work, loader edge cases."""

import os
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from homematic_exporter.config_models import Tuning
from homematic_exporter.metrics import ConfigError, Registry, load_config, parse_config
from homematic_exporter.metrics import config as config_module
from tests.metrics.conftest import metric
from tests.metrics.helpers import defs, device, parse, room, snapshot, valve

LEGIT = "Küche 👨‍👩‍👧"  # umlaut and a ZWJ emoji sequence


def full_registry(**kw: Any) -> Registry:
    labels = ["room", "device_type", "device"]
    return Registry.build(
        defs(
            metric(),
            metric(
                name="homematic_device_rssi_dbm", scope="devices", value="rssi_dbm", labels=labels
            ),
            metric(
                name="homematic_valve_position_ratio",
                scope="valves",
                value="position_ratio",
                labels=labels,
            ),
        ),
        Tuning(),
        **kw,
    )


@pytest.mark.parametrize(
    "name", ["bad\ud800", "x\x00y", "esc\x1b[31m", "line\nbreak", "‮evil", "a b", "\x85"]
)
def test_hostile_names_never_break_the_exposition(name: str) -> None:
    r = full_registry()
    r.update(
        snapshot(
            rooms=(room(name),),
            devices=(device(name, name),),
            valves=(valve(name, room=name),),
        )
    )
    text = r.exposition().decode("utf-8")  # must not raise
    for bad in ("\x00", "\x1b", "‮", " ", "\x85", "\ud800"):
        assert bad not in text
    assert len(parse(r.exposition())["homematic_room_temperature_celsius"]) == 1


def test_surrogate_version_does_not_break_scrapes() -> None:
    r = full_registry(version="v\udc80")
    assert b"homematic_exporter_build_info" in r.exposition()


def test_hostile_help_does_not_break_scrapes() -> None:
    with pytest.raises(ValidationError):  # lone surrogates never get into a definition
        defs(metric(help="bad\ud800"))
    r = Registry.build(defs(metric(help="bad\x00 help\x1b")), Tuning())
    r.update(snapshot(rooms=(room(),)))
    assert b"homematic_room_temperature_celsius" in r.exposition()


def test_huge_names_are_capped() -> None:
    r = full_registry()
    r.update(snapshot(rooms=(room("x" * 5_000_000),)))
    out = r.exposition()
    assert len(out) < 2000
    (labels,) = parse(out)["homematic_room_temperature_celsius"]
    assert len(labels[0][1]) == 200


def test_legitimate_unicode_is_unchanged() -> None:
    r = full_registry()
    r.update(snapshot(rooms=(room(LEGIT),)))
    assert parse(r.exposition())["homematic_room_temperature_celsius"] == {(("room", LEGIT),): 21.5}


def test_sanitising_can_merge_names_and_is_reported_as_duplicate() -> None:
    r = full_registry()
    r.update(snapshot(rooms=(room("a\x00"), room("a\x01"))))
    assert len(parse(r.exposition())["homematic_room_temperature_celsius"]) == 1


# --- bounded config work ---------------------------------------------------------------------


def test_huge_metrics_list_fails_fast_with_a_true_count(
    raw_config: dict[str, Any], tmp_path: Path
) -> None:
    entries = "\n".join("  - {a: 1}" for _ in range(20_000))
    text = yaml.safe_dump({k: v for k, v in raw_config.items() if k != "metrics"})
    path = tmp_path / "big.yaml"
    path.write_text(text + "metrics:\n" + entries + "\n")
    assert path.stat().st_size < 1024 * 1024
    start = time.monotonic()
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert time.monotonic() - start < 5
    assert "20000 entries" in str(info.value)
    assert "metrics" in info.value.issues[0].path


def test_issue_overflow_reports_the_true_count(raw_config: dict[str, Any]) -> None:
    raw_config["metrics"] = [
        metric(name=f"homematic_room_m{i}_celsius", labels=["bad"]) for i in range(500)
    ]
    with pytest.raises(ConfigError) as info:
        parse_config(raw_config)
    assert info.value.total == 500
    assert "and 480 more" in str(info.value)


def test_only_the_shown_issues_are_kept(raw_config: dict[str, Any]) -> None:
    raw_config["metrics"] = [{"x": 1} for _ in range(400)]
    with pytest.raises(ConfigError) as info:
        parse_config(raw_config)
    assert len(info.value.issues) == 20
    assert info.value.total >= 400


def test_a_one_mebibyte_file_is_rejected_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "huge.yaml"
    path.write_text("metrics:\n" + "  - {a: 1}\n" * 100_000)
    start = time.monotonic()
    with pytest.raises(ConfigError, match="too large"):
        load_config(path)
    assert time.monotonic() - start < 1


# --- loader edge cases -----------------------------------------------------------------------


def test_dangling_symlink_at_the_mount_path_does_not_fall_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = tmp_path / "config.yaml"
    link.symlink_to(tmp_path / "gone.yaml")
    monkeypatch.setattr(config_module, "MOUNT_CONFIG_PATH", link)
    with pytest.raises(ConfigError, match="not found"):
        load_config(None)


def test_unreadable_mount_parent_does_not_fall_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "locked"
    parent.mkdir()
    (parent / "config.yaml").write_text("version: 1\n")
    parent.chmod(0)
    monkeypatch.setattr(config_module, "MOUNT_CONFIG_PATH", parent / "config.yaml")
    try:
        if os.access(parent, os.R_OK | os.X_OK):
            pytest.skip("running as a user that ignores permissions")
        with pytest.raises(ConfigError):
            load_config(None)
    finally:
        parent.chmod(0o700)


def test_nul_in_the_path_is_a_config_error() -> None:
    with pytest.raises(ConfigError):
        load_config(Path("a\x00b"))


def test_newline_and_escape_keys_cannot_forge_log_lines(raw_config: dict[str, Any]) -> None:
    raw_config["evil\nERROR forged line"] = 1
    raw_config["esc\x1b[2J"] = 1
    with pytest.raises(ConfigError) as info:
        parse_config(raw_config)
    text = str(info.value)
    assert "\x1b" not in text
    assert all(not line.startswith("ERROR") for line in text.splitlines())
    assert len(text.splitlines()) == 3  # header plus the two issues


def test_token_like_keys_are_redacted(raw_config: dict[str, Any]) -> None:
    token = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"  # noqa: S105 (fake)
    raw_config[token] = 1
    raw_config["metrics"] = [metric(labels=[token])]
    with pytest.raises(ConfigError) as info:
        parse_config(raw_config)
    assert token not in str(info.value)


@pytest.mark.parametrize("version", [True, 1.0, "1"])
def test_version_must_be_the_integer_one(raw_config: dict[str, Any], version: object) -> None:
    raw_config["version"] = version
    with pytest.raises(ConfigError, match="version"):
        parse_config(raw_config)


def test_every_scope_label_has_an_attribute_mapping() -> None:
    from homematic_exporter.metrics.schema import SCOPE_LABELS
    from homematic_exporter.metrics.series import LABEL_ATTRS

    for scope, labels in SCOPE_LABELS.items():
        assert set(labels) <= set(LABEL_ATTRS[scope])
