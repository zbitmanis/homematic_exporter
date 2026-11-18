import json
import logging
import os
import stat
import threading
import time
from pathlib import Path

import pytest

from homematic_exporter.contracts import StateStore
from homematic_exporter.state import FileStateStore, StateDirError
from homematic_exporter.state.store import MAX_STATE_BYTES


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.mark.parametrize("umask", [0o022, 0o077, 0o000])
def test_creates_directory_0700(tmp_path: Path, umask: int) -> None:
    target = tmp_path / "state"
    old = os.umask(umask)
    try:
        FileStateStore(target)
    finally:
        os.umask(old)
    assert mode(target) == 0o700


def test_missing_parent_is_an_error_without_path(tmp_path: Path) -> None:
    target = tmp_path / "a" / "state"
    with pytest.raises(StateDirError) as exc:
        FileStateStore(target)
    assert str(tmp_path) not in str(exc.value)
    assert not (tmp_path / "a").exists()


def test_refuses_directory_owned_by_someone_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = tmp_path / "s"
    d.mkdir(mode=0o700)
    monkeypatch.setattr(os, "getuid", lambda: os.stat(d).st_uid + 1)
    with pytest.raises(StateDirError) as exc:
        FileStateStore(d)
    assert str(d) not in str(exc.value)


OLD = time.time() - 3600
STALE = ".battery.ab12_x9z.tmp"


def make_tmp(path: Path, mtime: float) -> None:
    path.write_text("partial")
    os.utime(path, (mtime, mtime))


def test_old_own_temp_file_removed_at_startup(tmp_path: Path) -> None:
    d = tmp_path / "s"
    FileStateStore(d)
    make_tmp(d / STALE, OLD)
    (d / "battery.json").write_text("{}")
    FileStateStore(d)
    assert [p.name for p in d.iterdir()] == ["battery.json"]


def test_young_own_temp_file_kept(tmp_path: Path) -> None:
    d = tmp_path / "s"
    FileStateStore(d)
    make_tmp(d / STALE, time.time() - 10)
    FileStateStore(d)
    assert (d / STALE).exists()


@pytest.mark.parametrize("name", [".notes.tmp", ".battery.tmp", "battery.ab12_x9z.tmp"])
def test_unrelated_old_tmp_files_kept(tmp_path: Path, name: str) -> None:
    d = tmp_path / "s"
    FileStateStore(d)
    make_tmp(d / name, OLD)
    FileStateStore(d)
    assert (d / name).exists()


def test_symlink_and_directory_with_temp_name_kept(tmp_path: Path) -> None:
    d = tmp_path / "s"
    FileStateStore(d)
    target = tmp_path / "target"
    target.write_text("x")
    (d / STALE).symlink_to(target)
    (d / ".k.zz99zz99.tmp").mkdir()
    FileStateStore(d)
    assert (d / STALE).is_symlink() and target.exists()
    assert (d / ".k.zz99zz99.tmp").is_dir()


def test_real_temp_name_matches_cleanup_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = tmp_path / "s"
    store = FileStateStore(d)
    seen: list[str] = []
    real = os.replace

    def spy(src: str, dst: str) -> None:
        seen.append(Path(src).name)
        real(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    store.save("battery", {})
    monkeypatch.undo()
    make_tmp(d / seen[0], OLD)
    FileStateStore(d)
    assert not (d / seen[0]).exists()


def _load_with_timeout(store: FileStateStore, key: str) -> list[object]:
    out: list[object] = []
    t = threading.Thread(target=lambda: out.append(store.load(key)), daemon=True)
    t.start()
    t.join(5)
    assert not t.is_alive(), "load hung"
    return out


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no mkfifo")
def test_fifo_state_file_does_not_hang(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    store = FileStateStore(tmp_path / "s")
    os.mkfifo(tmp_path / "s" / "k.json")
    with caplog.at_level(logging.WARNING):
        assert _load_with_timeout(store, "k") == [None]
    assert "not a regular file" in caplog.text
    assert str(tmp_path) not in caplog.text


def test_symlinked_state_file_rejected(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path / "s")
    real = tmp_path / "real.json"
    real.write_text('{"a": 1}')
    (tmp_path / "s" / "k.json").symlink_to(real)
    assert store.load("k") is None


def test_regular_state_file_still_loads(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path / "s")
    (tmp_path / "s" / "k.json").write_text('{"a": 1}')
    assert store.load("k") == {"a": 1}


def test_save_fsyncs_file_and_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = FileStateStore(tmp_path / "s")
    calls: list[int] = []
    real = os.fsync

    def counting_fsync(fd: int) -> None:
        calls.append(fd)
        real(fd)

    monkeypatch.setattr(os, "fsync", counting_fsync)
    store.save("k", {"v": 1})
    assert len(calls) == 2


def test_directory_fsync_failure_is_ignored_and_logged_at_debug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store = FileStateStore(tmp_path / "s")
    real_open = os.open

    def fail_dir_open(path: str | Path, flags: int, *a: int, **k: int) -> int:
        if flags == os.O_RDONLY:
            raise OSError("unsupported")
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr(os, "open", fail_dir_open)
    with caplog.at_level(logging.DEBUG, logger="homematic_exporter.state.store"):
        store.save("k", {"v": 1})
    monkeypatch.undo()
    debug = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert len(debug) == 1 and "OSError" in debug[0].getMessage()
    assert str(tmp_path) not in caplog.text
    assert store.load("k") == {"v": 1}


def test_oversized_file_treated_as_corrupt(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = FileStateStore(tmp_path / "s")
    (tmp_path / "s" / "k.json").write_bytes(b" " * (MAX_STATE_BYTES + 1) + b"{}")
    with caplog.at_level(logging.WARNING):
        assert store.load("k") is None
    assert len(caplog.records) == 1


@pytest.mark.parametrize(
    "content", [b'{"a": NaN}', b'{"a": Infinity}', b'{"a": -Infinity}', b"[" * 100000]
)
def test_non_finite_and_deeply_nested_are_corrupt(tmp_path: Path, content: bytes) -> None:
    store = FileStateStore(tmp_path / "s")
    (tmp_path / "s" / "k.json").write_bytes(content)
    assert store.load("k") is None


def test_save_rejects_non_finite(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path / "s")
    with pytest.raises(ValueError):
        store.save("k", {"v": float("nan")})
    assert list((tmp_path / "s").iterdir()) == []


def test_key_length_limit(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path / "s")
    store.save("a" * 64, {"v": 1})
    assert store.load("a" * 64) == {"v": 1}
    with pytest.raises(ValueError):
        store.save("a" * 65, {})
    with pytest.raises(ValueError):
        store.load("a" * 65)


def test_non_str_key_rejected(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path / "s")
    with pytest.raises(ValueError):
        store.save(1, {})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        store.load(None)  # type: ignore[arg-type]


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
    with pytest.raises(StateDirError, match="not a directory") as exc:
        FileStateStore(f)
    assert str(tmp_path) not in str(exc.value)


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
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert str(tmp_path) not in caplog.text


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


@pytest.mark.skipif(not os.path.isdir("/dev/fd"), reason="no /dev/fd")
def test_rejected_state_files_do_not_leak_descriptors(tmp_path: Path) -> None:
    store = FileStateStore(tmp_path / "s")
    (tmp_path / "s" / "k.json").mkdir()
    before = len(os.listdir("/dev/fd"))
    for _ in range(200):
        assert store.load("k") is None
    assert len(os.listdir("/dev/fd")) == before


def test_dangling_symlink_at_state_path(tmp_path: Path) -> None:
    link = tmp_path / "s"
    link.symlink_to(tmp_path / "missing")
    with pytest.raises(StateDirError) as exc:
        FileStateStore(link)
    assert str(tmp_path) not in str(exc.value)
