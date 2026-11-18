import json
import logging
import os
import stat
from pathlib import Path

import pytest

from homematic_exporter.contracts import StateStore
from homematic_exporter.state import FileStateStore, StateDirError


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_creates_directory_0700(tmp_path: Path) -> None:
    target = tmp_path / "a" / "state"
    FileStateStore(target)
    assert mode(target) == 0o700


def test_accepts_existing_0700_dir(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    FileStateStore(tmp_path)


@pytest.mark.parametrize("bad", [0o755, 0o770, 0o707, 0o750])
def test_refuses_looser_directory(tmp_path: Path, bad: int) -> None:
    d = tmp_path / "s"
    d.mkdir()
    d.chmod(bad)
    with pytest.raises(StateDirError) as exc:
        FileStateStore(d)
    assert str(d) not in str(exc.value)


def test_refuses_non_directory(tmp_path: Path) -> None:
    f = tmp_path / "file"
    f.write_text("x")
    with pytest.raises(StateDirError):
        FileStateStore(f)


def test_conforms_to_protocol(tmp_path: Path) -> None:
    assert isinstance(FileStateStore(tmp_path / "s"), StateStore)


def test_round_trip_and_file_mode(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path / "s")
    store.save("battery", {"a": 1, "b": [1, 2]})
    assert store.load("battery") == {"a": 1, "b": [1, 2]}
    assert mode(tmp_path / "s" / "battery.json") == 0o600


def test_overwrite_keeps_mode_and_leaves_no_temp_files(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path / "s")
    store.save("k", {"v": 1})
    store.save("k", {"v": 2})
    assert store.load("k") == {"v": 2}
    assert [p.name for p in (tmp_path / "s").iterdir()] == ["k.json"]
    assert mode(tmp_path / "s" / "k.json") == 0o600


def test_missing_key_returns_none(tmp_path: Path) -> None:
    assert FileStateStore(tmp_path / "s").load("nope") is None


def test_failed_write_keeps_old_value_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileStateStore(tmp_path / "s")
    store.save("k", {"v": 1})

    def boom(src: object, dst: object) -> None:
        raise OSError("disk")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        store.save("k", {"v": 2})
    monkeypatch.undo()
    assert store.load("k") == {"v": 1}
    assert [p.name for p in (tmp_path / "s").iterdir()] == ["k.json"]


def test_unserialisable_value_leaves_no_file(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path / "s")
    with pytest.raises(TypeError):
        store.save("k", {"v": object()})
    assert list((tmp_path / "s").iterdir()) == []


@pytest.mark.parametrize("content", [b"{not json", b"[1, 2]", b"\xff\xfe", b""])
def test_corrupt_file_returns_none_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, content: bytes
) -> None:
    store = FileStateStore(tmp_path / "s")
    (tmp_path / "s" / "k.json").write_bytes(content)
    with caplog.at_level(logging.WARNING, logger="homematic_exporter.state.store"):
        assert store.load("k") is None
    assert len(caplog.records) == 1
    assert "not json" not in caplog.text


def test_unreadable_file_returns_none(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = FileStateStore(tmp_path / "s")
    (tmp_path / "s" / "k.json").mkdir()  # reading a directory raises OSError
    with caplog.at_level(logging.WARNING):
        assert store.load("k") is None
    assert caplog.records


@pytest.mark.parametrize(
    "key", ["../x", "a/b", "..", "a..b", "", ".hidden", "a\\b", "/abs", "a\x00"]
)
def test_unsafe_keys_rejected(tmp_path: Path, key: str) -> None:
    store = FileStateStore(tmp_path / "s")
    with pytest.raises(ValueError):
        store.save(key, {})
    with pytest.raises(ValueError):
        store.load(key)
    assert not (tmp_path / "x.json").exists()


def test_saved_file_is_json(tmp_path: Path) -> None:
    FileStateStore(tmp_path / "s").save("k", {"a": None})
    assert json.loads((tmp_path / "s" / "k.json").read_text()) == {"a": None}
