import json
import logging
import os
from pathlib import Path
from typing import Any

import pytest

from homematic_exporter.config_models import ExtractConfig
from homematic_exporter.contracts import NameCollisionError, Source, UpstreamError
from homematic_exporter.source import FileSource
from homematic_exporter.source.file_source import MAX_FILE_BYTES

NOW = 1_795_000_000.0


def write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data))
    return path


def make(path: Path, extract: ExtractConfig) -> FileSource:
    return FileSource(path, extract, clock=lambda: NOW)


def test_implements_source_protocol(tmp_path: Path, default_extract: ExtractConfig) -> None:
    assert isinstance(make(tmp_path / "x.json", default_extract), Source)


async def test_fetch_parses_the_file(
    tmp_path: Path, mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    source = make(write(tmp_path / "state.json", mini_state), default_extract)
    snap = await source.fetch()
    assert snap.taken_at == NOW
    assert [r.name for r in snap.rooms] == ["kitchen", "bedroom", "hall"]
    assert len(snap.devices) == 10


async def test_fetch_rereads_the_file_each_time(
    tmp_path: Path, mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    path = write(tmp_path / "state.json", mini_state)
    source = make(path, default_extract)
    await source.fetch()
    mini_state["groups"]["ID-0201"]["actualTemperature"] = 25.0
    write(path, mini_state)
    assert (await source.fetch()).rooms[0].temperature_celsius == 25.0


async def test_default_clock_is_wall_time(
    tmp_path: Path, mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    snap = await FileSource(write(tmp_path / "s.json", mini_state), default_extract).fetch()
    assert snap.taken_at > 1_700_000_000


async def test_missing_file_is_upstream_error_without_path(
    tmp_path: Path, default_extract: ExtractConfig
) -> None:
    secret_dir = tmp_path / "very-private-dir"
    with pytest.raises(UpstreamError) as err:
        await make(secret_dir / "nope.json", default_extract).fetch()
    assert "very-private-dir" not in str(err.value) + err.value.body


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"{not json",
        b"\xff\xfe\x00",
        b'{"devices": {}, "groups": {}, "x": NaN}',
        b'{"devices": {}, "groups": {}, "x": Infinity}',
        b"[" * 200_000,
        b'{"x": ' + b"9" * 10_000 + b"}",
        b"[]",
        b'"string"',
        b"null",
    ],
)
async def test_invalid_content_is_upstream_error(
    tmp_path: Path, default_extract: ExtractConfig, content: bytes
) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(content)
    with pytest.raises(UpstreamError):
        await make(path, default_extract).fetch()


async def test_oversized_file_is_rejected_without_reading_it_all(
    tmp_path: Path, default_extract: ExtractConfig
) -> None:
    path = tmp_path / "big.json"
    path.write_bytes(b" " * (MAX_FILE_BYTES + 1))
    with pytest.raises(UpstreamError, match="too large"):
        await make(path, default_extract).fetch()


async def test_file_at_the_limit_is_accepted(
    tmp_path: Path, default_extract: ExtractConfig
) -> None:
    body = b'{"devices": {}, "groups": {}}'
    path = tmp_path / "ok.json"
    path.write_bytes(body + b" " * (MAX_FILE_BYTES - len(body)))
    assert (await make(path, default_extract).fetch()).devices == ()


async def test_symlink_is_rejected(
    tmp_path: Path, mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    target = write(tmp_path / "real.json", mini_state)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(UpstreamError):
        await make(link, default_extract).fetch()


async def test_directory_is_rejected(tmp_path: Path, default_extract: ExtractConfig) -> None:
    with pytest.raises(UpstreamError):
        await make(tmp_path, default_extract).fetch()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs mkfifo")
async def test_fifo_is_rejected_without_blocking(
    tmp_path: Path, default_extract: ExtractConfig
) -> None:
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(UpstreamError):
        await make(fifo, default_extract).fetch()


async def test_duplicate_json_keys_last_wins(
    tmp_path: Path, default_extract: ExtractConfig
) -> None:
    path = tmp_path / "dup.json"
    path.write_text('{"devices": {"a": 1}, "devices": {}, "groups": {}}')
    assert (await make(path, default_extract).fetch()).devices == ()


async def test_collision_policy_is_honoured(
    tmp_path: Path, collision_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    source = make(write(tmp_path / "c.json", collision_state), default_extract)
    with pytest.raises(NameCollisionError):
        await source.fetch("error")
    snap = await source.fetch("suffix")
    assert "kitchen wall-thermostat-2" in {d.name for d in snap.devices}


async def test_collision_warning_once_per_new_collision(
    tmp_path: Path,
    collision_state: dict[str, Any],
    mini_state: dict[str, Any],
    default_extract: ExtractConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = write(tmp_path / "c.json", collision_state)
    source = make(path, default_extract)
    caplog.set_level(logging.DEBUG)

    await source.fetch("suffix")
    await source.fetch("suffix")  # same collision again: silent
    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "name collision" in r.getMessage()
    ]
    assert len(warnings) == 1
    assert "kitchen wall-thermostat" in warnings[0].getMessage()
    assert "device name collision" not in warnings[0].getMessage()  # it also covers rooms
    assert "SGTIN" not in warnings[0].getMessage()

    write(path, mini_state)  # collision resolved ...
    await source.fetch("suffix")
    write(path, collision_state)  # ... and back: a new collision, warn again
    await source.fetch("suffix")
    warnings = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "name collision" in r.getMessage()
    ]
    assert len(warnings) == 2


async def test_error_policy_does_not_log_a_warning(
    tmp_path: Path,
    collision_state: dict[str, Any],
    default_extract: ExtractConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = make(write(tmp_path / "c.json", collision_state), default_extract)
    with pytest.raises(NameCollisionError), caplog.at_level(logging.DEBUG):
        await source.fetch("error")
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


async def test_unmapped_model_warned_once(
    tmp_path: Path,
    mini_state: dict[str, Any],
    default_extract: ExtractConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = make(write(tmp_path / "s.json", mini_state), default_extract)
    caplog.set_level(logging.DEBUG)
    await source.fetch()
    await source.fetch()
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(messages) == 1
    assert "HmIP-NEW-1" in messages[0]


async def test_hostile_model_string_is_bounded_in_the_log(
    tmp_path: Path,
    default_extract: ExtractConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state = {
        "groups": {},
        "devices": {"a": {"modelType": "X" * 5000 + "\nFORGED LOG LINE"}},
    }
    source = make(write(tmp_path / "s.json", state), default_extract)
    caplog.set_level(logging.DEBUG)
    await source.fetch()
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert len(text) < 500
    assert "\nFORGED" not in text


async def test_path_with_nul_byte_is_upstream_error(default_extract: ExtractConfig) -> None:
    with pytest.raises(UpstreamError):
        await make(Path("a\0b.json"), default_extract).fetch()


@pytest.mark.parametrize("content", [b"{bad", b"[" * 200_000, b'{"x": NaN}'])
async def test_errors_leave_no_context(
    tmp_path: Path, default_extract: ExtractConfig, content: bytes
) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(content)
    with pytest.raises(UpstreamError) as err:
        await make(path, default_extract).fetch()
    assert err.value.__context__ is None
    assert err.value.__cause__ is None


async def test_open_errors_leave_no_context(tmp_path: Path, default_extract: ExtractConfig) -> None:
    with pytest.raises(UpstreamError) as err:
        await make(tmp_path / "missing.json", default_extract).fetch()
    assert err.value.__context__ is None


async def test_sgtin_straddling_the_log_cut_is_not_partially_logged(
    tmp_path: Path, default_extract: ExtractConfig, caplog: pytest.LogCaptureFixture
) -> None:
    sgtin = "0123456789ABCDEF01234567"
    model = "M" * 49 + "-" + sgtin  # the 64-char cut would keep only 14 hex digits of it
    state = {"groups": {}, "devices": {"a": {"modelType": model}}}
    caplog.set_level(logging.DEBUG)
    await make(write(tmp_path / "s.json", state), default_extract).fetch()
    assert "0123456789abcd" not in caplog.text.lower()
