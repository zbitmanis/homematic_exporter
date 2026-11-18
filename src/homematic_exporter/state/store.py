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
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class StateDirError(Exception):
    """The state directory cannot be used (not a directory, or permissions too loose)."""


class FileStateStore:
    """One JSON file per key under `directory`. Never echoes stored values."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        try:
            self._dir.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
            st = self._dir.stat()
        except OSError as exc:
            raise StateDirError(f"cannot prepare state directory: {type(exc).__name__}") from None
        if not stat.S_ISDIR(st.st_mode):
            raise StateDirError("state path is not a directory")
        if stat.S_IMODE(st.st_mode) & 0o077:
            raise StateDirError("state directory permissions are too loose (need 0700)")
        if st.st_uid != os.getuid():
            raise StateDirError("state directory is not owned by the current user")

    def _path(self, key: str) -> Path:
        if not _KEY_RE.fullmatch(key) or ".." in key:
            raise ValueError("invalid state key")
        return self._dir / f"{key}.json"

    def load(self, key: str) -> dict[str, object] | None:
        path = self._path(key)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("state key %r unreadable (%s); starting empty", key, type(exc).__name__)
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            logger.warning("state key %r is corrupt; starting empty", key)
            return None
        if not isinstance(data, dict):
            logger.warning("state key %r has an unexpected shape; starting empty", key)
            return None
        return data

    def save(self, key: str, value: dict[str, object]) -> None:
        path = self._path(key)
        payload = json.dumps(value, sort_keys=True)
        fd, tmp_name = tempfile.mkstemp(dir=self._dir, prefix=f".{key}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), _FILE_MODE)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
