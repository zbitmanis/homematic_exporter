"""File-backed `StateStore` (spec 3, R12): dir 0700, files 0600, atomic writes."""

import json
import logging
import os
import re
import stat
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_DIR_MODE = 0o700
_FILE_MODE = 0o600
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
MAX_STATE_BYTES = 1_000_000


class StateDirError(Exception):
    """The state directory cannot be used (not a directory, or permissions too loose)."""


def _reject_constant(name: str) -> object:
    raise ValueError("non-finite number")


class FileStateStore:
    """One JSON file per key under `directory`. Never echoes stored values."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        try:
            self._dir.mkdir(mode=_DIR_MODE, exist_ok=True)
            st = self._dir.stat()
        except FileNotFoundError:
            raise StateDirError("state directory parent does not exist") from None
        except OSError as exc:
            raise StateDirError(f"cannot prepare state directory: {type(exc).__name__}") from None
        if not stat.S_ISDIR(st.st_mode):
            raise StateDirError("state path is not a directory")
        if stat.S_IMODE(st.st_mode) & 0o077:
            raise StateDirError("state directory permissions are too loose (need 0700)")
        if st.st_uid != os.getuid():
            raise StateDirError("state directory is not owned by the current user")
        self._remove_stale_temp_files()

    def _remove_stale_temp_files(self) -> None:
        """Best effort: drop `.<key>.*.tmp` files left by a hard crash mid-write."""
        try:
            for path in self._dir.glob(".*.tmp"):
                if path.is_file() and not path.is_symlink():
                    path.unlink(missing_ok=True)
        except OSError:
            logger.warning("could not clean stale state temp files")

    def _path(self, key: str) -> Path:
        if not isinstance(key, str) or not _KEY_RE.fullmatch(key) or ".." in key:
            raise ValueError("invalid state key")
        return self._dir / f"{key}.json"

    def load(self, key: str) -> dict[str, object] | None:
        path = self._path(key)
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_STATE_BYTES + 1)
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning("state key %r unreadable (%s); starting empty", key, type(exc).__name__)
            return None
        if len(raw) > MAX_STATE_BYTES:
            logger.warning("state key %r is too large; starting empty", key)
            return None
        try:
            data = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
        except (ValueError, RecursionError):
            logger.warning("state key %r is corrupt; starting empty", key)
            return None
        if not isinstance(data, dict):
            logger.warning("state key %r has an unexpected shape; starting empty", key)
            return None
        return data

    def _fsync_dir(self) -> None:
        try:
            fd = os.open(self._dir, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)

    def save(self, key: str, value: dict[str, object]) -> None:
        path = self._path(key)
        payload = json.dumps(value, sort_keys=True, allow_nan=False)
        fd, tmp_name = tempfile.mkstemp(dir=self._dir, prefix=f".{key}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), _FILE_MODE)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
            self._fsync_dir()
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
