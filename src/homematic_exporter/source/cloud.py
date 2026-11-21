"""`Source` over the Homematic IP cloud (read-only), using `homematicip` 2.23.1.

Only the library's public async API is used: `AsyncHome.init_async` and
`download_configuration_async()`. The raw JSON it returns is parsed by `parser.py`, so the
library's object model is not a dependency. The library (GPL-3.0) is imported lazily, so the
file source and the parser work without loading it.
"""

import asyncio
import importlib
import math
import re
import time
from collections.abc import Callable
from typing import Any, Protocol

from homematic_exporter.config_models import ExtractConfig
from homematic_exporter.contracts import CollisionPolicy, Snapshot, UpstreamError
from homematic_exporter.redact import scrub
from homematic_exporter.source.builder import SnapshotBuilder

MAX_BODY_CHARS = 2000  # what an UpstreamError body keeps, after scrubbing
_MAX_SCRUBBED_INPUT = 64 * 1024  # bound the text handed to `scrub`
_STATUS_IN_MESSAGE = re.compile(r"\bError: ([1-5]\d\d)\b")
_STATUS_BY_CLASS = {"HmipAuthenticationError": 403, "HmipThrottlingError": 429}


def _escape(text: str) -> str:
    """Escape control characters (newline, ESC, ...) so a body cannot forge log lines."""
    return "".join(c if c.isprintable() else c.encode("unicode_escape").decode() for c in text)


class _Home(Protocol):
    """The slice of `homematicip.async_home.AsyncHome` this module uses."""

    async def init_async(self, access_point_id: str, auth_token: str) -> None: ...

    async def download_configuration_async(self) -> Any: ...


def _status_of(exc: BaseException) -> int | None:
    for cls in type(exc).__mro__:
        if (status := _STATUS_BY_CLASS.get(cls.__name__)) is not None:
            return status
    match = _STATUS_IN_MESSAGE.search(_message_of(exc))
    return int(match.group(1)) if match else None


def _message_of(exc: BaseException) -> str:
    try:
        return str(exc)[:_MAX_SCRUBBED_INPUT]
    except Exception:  # a hostile __str__ must not break error handling
        return ""


class CloudSource:
    """Fetches the configuration with the access-point token. One instance, one poll task.

    `fetch` calls are sequential (the poll loop); concurrent calls are not supported. Credentials
    are kept in private attributes and never appear in `repr`, errors or logs.
    """

    def __init__(
        self,
        access_point: str,
        token: str,
        timeout: float,
        extract: ExtractConfig,
        *,
        home_factory: Callable[[], _Home] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        access_point, token = access_point.strip(), token.strip()  # e.g. a secret file's newline
        if not access_point or not token:
            raise ValueError("access point and token must not be empty")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive, finite number of seconds")
        self._access_point = access_point
        self._token = token
        self._timeout = timeout
        self._clock = clock
        self._home_factory = home_factory or self._new_home
        self._home: _Home | None = None
        self._builder = SnapshotBuilder(extract)

    def __repr__(self) -> str:
        return "CloudSource(...)"

    @staticmethod
    def _new_home() -> _Home:
        module = importlib.import_module("homematicip.async_home")
        home: _Home = module.AsyncHome()
        return home

    def _upstream_error(self, exc: BaseException) -> UpstreamError:
        """A typed error whose message and body are free of the credentials and SGTINs."""
        if isinstance(exc, TimeoutError):
            return UpstreamError(
                "cloud request timed out", body=f"no answer within {self._timeout:g} seconds"
            )
        text = f"{type(exc).__name__}: {_message_of(exc)}"
        body = _escape(scrub(text, (self._token, self._access_point)))[:MAX_BODY_CHARS]
        status = _status_of(exc)
        suffix = f" (HTTP {status})" if status is not None else ""
        return UpstreamError(f"cloud request failed{suffix}", status=status, body=body)

    async def _download(self) -> object:
        home = self._home
        if home is None:
            # The first call imports the (slow) library: keep that off the event loop.
            home = await asyncio.to_thread(self._home_factory)
            async with asyncio.timeout(self._timeout):
                await home.init_async(self._access_point, self._token)
            self._home = home
        async with asyncio.timeout(self._timeout):
            result: object = await home.download_configuration_async()
        return result

    async def fetch(self, on_collision: CollisionPolicy = "error") -> Snapshot:
        failure: UpstreamError | None = None
        try:
            raw = await self._download()
        except Exception as exc:  # CancelledError is a BaseException and propagates
            self._home = None  # re-run the URL lookup next time
            failure = self._upstream_error(exc)
        if failure is not None:
            raise failure  # outside the except block: no __context__ keeps the library error
        rejected: UpstreamError | None = None
        try:
            return self._builder.build(raw, self._clock(), on_collision)
        except UpstreamError as exc:  # e.g. not a configuration: the parser cannot know the secrets
            body = scrub(exc.body, (self._token, self._access_point))[:MAX_BODY_CHARS]
            rejected = UpstreamError(str(exc), status=exc.status, body=body)
        raise rejected
