"""`Source` reading the raw configuration JSON from a local file (e2e tests, demos)."""

import asyncio
import json
import os
import stat
import time
from collections.abc import Callable
from pathlib import Path

from homematic_exporter.config_models import ExtractConfig
from homematic_exporter.contracts import CollisionPolicy, Snapshot, UpstreamError
from homematic_exporter.source.builder import SnapshotBuilder

# The full capture of the real installation is about 130 KB; this is generous, not unbounded.
MAX_FILE_BYTES = 8 * 1024 * 1024


def _reject_constant(name: str) -> object:
    raise ValueError("non-finite number")


class _Rejected(Exception):
    """Internal: the file is unusable for a reason that is safe to report."""


def _slurp(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)  # OSError, or ValueError for an embedded NUL
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise _Rejected("configuration file is not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_FILE_BYTES:
        raise _Rejected("configuration file too large")
    return data


def _read_file(path: Path) -> bytes:
    """Blocking read of a regular file (no symlink, no special file) of at most MAX_FILE_BYTES.

    The `UpstreamError` is raised after the `except` block, so it carries no `__context__`.
    """
    try:
        return _slurp(path)
    except _Rejected as rejected:
        reason = str(rejected)
    except (OSError, ValueError) as exc:  # ValueError: embedded NUL in the path
        reason = f"cannot read configuration file: {type(exc).__name__}"
    raise UpstreamError(reason)


def _load(path: Path) -> object:
    data = _read_file(path)
    try:
        return json.loads(data, parse_constant=_reject_constant)
    except (ValueError, RecursionError):  # includes JSONDecodeError, UnicodeDecodeError
        pass
    raise UpstreamError("configuration file is not valid JSON")


class FileSource:
    """Reads the file on every `fetch` (in a worker thread, so the loop is never blocked)."""

    def __init__(
        self,
        path: str | Path,
        extract: ExtractConfig,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = Path(path)
        self._clock = clock
        self._builder = SnapshotBuilder(extract)

    async def fetch(self, on_collision: CollisionPolicy = "error") -> Snapshot:
        raw = await asyncio.to_thread(_load, self._path)
        return self._builder.build(raw, self._clock(), on_collision)
