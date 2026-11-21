import asyncio
import importlib
import logging
from typing import Any

import pytest

from homematic_exporter.config_models import ExtractConfig
from homematic_exporter.contracts import NameCollisionError, Source, UpstreamError
from homematic_exporter.source import CloudSource
from homematic_exporter.source.cloud import MAX_BODY_CHARS

NOW = 1_795_000_000.0
TOKEN = "Tok3n-s3cr3t-VALUE-0123456789"  # noqa: S105 (fake)
ACCESS_POINT = "3014F711A000ABCDEF123456"


class AuthenticationError(Exception):
    """Same class name as the library's, so the status mapping is exercised without the import."""


AuthenticationError.__name__ = "HmipAuthenticationError"


class FakeHome:
    """Stands in for `AsyncHome`: no network. `download` is a coroutine factory."""

    instances: list["FakeHome"] = []

    def __init__(self, state: Any = None, init_error: BaseException | None = None) -> None:
        self.state = state
        self.init_error = init_error
        self.init_calls: list[tuple[str, str]] = []
        self.download_calls = 0
        self.hang_init = False
        self.hang_download = False
        self.download_error: BaseException | None = None

    async def init_async(self, access_point_id: str, auth_token: str) -> None:
        self.init_calls.append((access_point_id, auth_token))
        if self.hang_init:
            await asyncio.sleep(3600)
        if self.init_error is not None:
            raise self.init_error

    async def download_configuration_async(self) -> Any:
        self.download_calls += 1
        if self.hang_download:
            await asyncio.sleep(3600)
        if self.download_error is not None:
            raise self.download_error
        return self.state


def make(
    home: FakeHome,
    extract: ExtractConfig,
    timeout: float = 5.0,
    factory_calls: list[int] | None = None,
) -> CloudSource:
    def factory() -> FakeHome:
        if factory_calls is not None:
            factory_calls.append(1)
        return home

    return CloudSource(
        ACCESS_POINT, TOKEN, timeout, extract, home_factory=factory, clock=lambda: NOW
    )


def test_implements_source_protocol(default_extract: ExtractConfig) -> None:
    assert isinstance(make(FakeHome(), default_extract), Source)


async def test_fetch_downloads_and_parses(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    home = FakeHome(mini_state)
    snap = await make(home, default_extract).fetch()
    assert snap.taken_at == NOW
    assert len(snap.devices) == 10
    assert home.init_calls == [(ACCESS_POINT, TOKEN)]


async def test_home_is_initialised_once_and_reused(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    home = FakeHome(mini_state)
    calls: list[int] = []
    source = make(home, default_extract, factory_calls=calls)
    await source.fetch()
    await source.fetch()
    assert len(home.init_calls) == 1
    assert home.download_calls == 2
    assert len(calls) == 1


async def test_failed_poll_reinitialises_the_home_next_time(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    home = FakeHome(mini_state)
    calls: list[int] = []
    source = make(home, default_extract, factory_calls=calls)
    await source.fetch()
    home.download_error = RuntimeError("boom")
    with pytest.raises(UpstreamError):
        await source.fetch()
    home.download_error = None
    await source.fetch()
    assert len(calls) == 2


async def test_init_failure_is_upstream_error(default_extract: ExtractConfig) -> None:
    home = FakeHome(init_error=OSError("dns failure"))
    with pytest.raises(UpstreamError):
        await make(home, default_extract).fetch()
    assert home.download_calls == 0


async def test_download_error_carries_status_and_scrubbed_body(
    default_extract: ExtractConfig,
) -> None:
    home = FakeHome()
    home.download_error = AuthenticationError(
        "Could not get the current configuration. Error: 403 Forbidden "
        f'({{"errorCode": "INVALID_TOKEN", "authToken": "{TOKEN}", "id": "{ACCESS_POINT}"}})'
    )
    with pytest.raises(UpstreamError) as err:
        await make(home, default_extract).fetch()
    assert err.value.status == 403
    assert "INVALID_TOKEN" in err.value.body  # useful part survives
    for secret in (TOKEN, ACCESS_POINT):
        assert secret not in err.value.body
        assert secret not in str(err.value)


async def test_status_is_read_from_the_library_message(default_extract: ExtractConfig) -> None:
    home = FakeHome()
    home.download_error = RuntimeError(
        "Could not get the current configuration. Error: 502 Bad Gateway"
    )
    with pytest.raises(UpstreamError) as err:
        await make(home, default_extract).fetch()
    assert err.value.status == 502
    assert "502" in err.value.body


async def test_unknown_error_has_no_status_and_no_traceback_chain(
    default_extract: ExtractConfig,
) -> None:
    home = FakeHome()
    home.download_error = ValueError(f"bad things with {TOKEN}")
    with pytest.raises(UpstreamError) as err:
        await make(home, default_extract).fetch()
    assert err.value.status is None
    assert TOKEN not in err.value.body
    assert err.value.__cause__ is None
    assert err.value.__context__ is None


def _real_errors(default_extract: ExtractConfig) -> list[BaseException]:
    conn = importlib.import_module("homematicip.exceptions.connection_exceptions")
    httpx2 = importlib.import_module("httpx2")
    msg = f"failure {TOKEN} {ACCESS_POINT}"
    return [
        conn.HmipAuthenticationError(msg),
        conn.HmipConnectionError(msg),
        conn.HmipThrottlingError(msg),
        httpx2.ConnectError(msg),
    ]


@pytest.mark.parametrize("index", range(4))
async def test_real_library_errors_leave_no_context_and_no_secret(
    index: int, default_extract: ExtractConfig
) -> None:
    home = FakeHome()
    home.download_error = _real_errors(default_extract)[index]
    with pytest.raises(UpstreamError) as err:
        await make(home, default_extract).fetch()
    assert err.value.__context__ is None
    assert err.value.__cause__ is None
    assert TOKEN not in err.value.body + str(err.value)
    assert ACCESS_POINT not in err.value.body + str(err.value)


async def test_init_error_leaves_no_context(default_extract: ExtractConfig) -> None:
    with pytest.raises(UpstreamError) as err:
        await make(FakeHome(init_error=OSError(TOKEN)), default_extract).fetch()
    assert err.value.__context__ is None


async def test_timeout_body_names_the_timeout(default_extract: ExtractConfig) -> None:
    home = FakeHome()
    home.hang_download = True
    with pytest.raises(UpstreamError) as err:
        await make(home, default_extract, timeout=0.05).fetch()
    assert "0.05" in err.value.body
    assert err.value.__context__ is None


async def test_payload_error_body_names_the_type_and_keys(default_extract: ExtractConfig) -> None:
    with pytest.raises(UpstreamError) as err:
        await make(FakeHome({"errorCode": "X", "secretvalue": "v"}), default_extract).fetch()
    assert "dict" in err.value.body
    assert "errorCode" in err.value.body
    assert '"v"' not in err.value.body


async def test_body_control_characters_are_escaped(default_extract: ExtractConfig) -> None:
    home = FakeHome()
    home.download_error = RuntimeError("line1\nFORGED\x1b[31mred")
    with pytest.raises(UpstreamError) as err:
        await make(home, default_extract).fetch()
    assert err.value.body.isprintable()
    assert "FORGED" in err.value.body


async def test_credentials_are_stripped_so_a_trailing_newline_is_still_redacted(
    default_extract: ExtractConfig,
) -> None:
    home = FakeHome()
    home.download_error = RuntimeError("echo tok and ap1")
    source = CloudSource("ap1\n", "tok\n", 1.0, default_extract, home_factory=lambda: home)
    with pytest.raises(UpstreamError) as err:
        await source.fetch()
    assert "tok" not in err.value.body
    assert "ap1" not in err.value.body
    assert home.init_calls == [("ap1", "tok")]


async def test_first_home_is_created_off_the_event_loop(default_extract: ExtractConfig) -> None:
    import threading

    seen: list[int] = []

    def factory() -> FakeHome:
        seen.append(threading.get_ident())
        return FakeHome({"devices": {}, "groups": {}})

    source = CloudSource(ACCESS_POINT, TOKEN, 1.0, default_extract, home_factory=factory)
    await source.fetch()
    assert seen and seen[0] != threading.get_ident()


async def test_secret_in_init_error_is_scrubbed(default_extract: ExtractConfig) -> None:
    home = FakeHome(init_error=ConnectionError(f"GET https://x/?ap={ACCESS_POINT}&t={TOKEN}"))
    with pytest.raises(UpstreamError) as err:
        await make(home, default_extract).fetch()
    assert TOKEN not in err.value.body + str(err.value)
    assert ACCESS_POINT not in err.value.body + str(err.value)


async def test_body_is_bounded(default_extract: ExtractConfig) -> None:
    home = FakeHome()
    home.download_error = RuntimeError("x" * 5_000_000)
    with pytest.raises(UpstreamError) as err:
        await make(home, default_extract).fetch()
    assert 0 < len(err.value.body) <= MAX_BODY_CHARS


@pytest.mark.parametrize("hang", ["init", "download"])
async def test_every_call_has_a_timeout(
    hang: str, mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    home = FakeHome(mini_state)
    setattr(home, f"hang_{hang}", True)
    with pytest.raises(UpstreamError, match="timed out"):
        await asyncio.wait_for(make(home, default_extract, timeout=0.05).fetch(), 2)


async def test_cancellation_propagates(default_extract: ExtractConfig) -> None:
    home = FakeHome()
    home.hang_download = True
    task = asyncio.create_task(make(home, default_extract).fetch())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancellation_during_init_propagates(default_extract: ExtractConfig) -> None:
    home = FakeHome()
    home.hang_init = True
    task = asyncio.create_task(make(home, default_extract).fetch())
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize("payload", [None, [], "x", 3, {}, {"devices": {}}])
async def test_wrong_payload_is_upstream_error(
    payload: Any, default_extract: ExtractConfig
) -> None:
    with pytest.raises(UpstreamError):
        await make(FakeHome(payload), default_extract).fetch()


async def test_collision_policy_passes_through_unwrapped(
    collision_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    source = make(FakeHome(collision_state), default_extract)
    with pytest.raises(NameCollisionError):
        await source.fetch("error")
    snap = await source.fetch("suffix")
    assert "kitchen wall-thermostat-2" in {d.name for d in snap.devices}


async def test_collision_warns_once_without_secrets(
    collision_state: dict[str, Any],
    default_extract: ExtractConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = make(FakeHome(collision_state), default_extract)
    caplog.set_level(logging.DEBUG)
    await source.fetch("suffix")
    await source.fetch("suffix")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert text.count("name collision") == 1
    for secret in (TOKEN, ACCESS_POINT, "SGTIN"):
        assert secret not in text


async def test_nothing_is_logged_with_secrets_on_failure(
    default_extract: ExtractConfig, caplog: pytest.LogCaptureFixture
) -> None:
    home = FakeHome()
    home.download_error = RuntimeError(TOKEN)
    caplog.set_level(logging.DEBUG)
    with pytest.raises(UpstreamError):
        await make(home, default_extract).fetch()
    assert TOKEN not in caplog.text


def test_repr_hides_credentials(default_extract: ExtractConfig) -> None:
    text = repr(make(FakeHome(), default_extract)) + str(make(FakeHome(), default_extract))
    assert TOKEN not in text
    assert ACCESS_POINT not in text


@pytest.mark.parametrize(
    ("access_point", "token", "timeout"),
    [
        ("", TOKEN, 1.0),
        (ACCESS_POINT, "", 1.0),
        ("  ", TOKEN, 1.0),
        (ACCESS_POINT, TOKEN, 0),
        (ACCESS_POINT, TOKEN, -1),
        (ACCESS_POINT, TOKEN, float("nan")),
        (ACCESS_POINT, TOKEN, float("inf")),
    ],
)
def test_constructor_validates_without_echoing_secrets(
    access_point: str, token: str, timeout: float, default_extract: ExtractConfig
) -> None:
    with pytest.raises(ValueError) as err:
        CloudSource(access_point, token, timeout, default_extract)
    assert TOKEN not in str(err.value)
    assert ACCESS_POINT not in str(err.value)


def test_default_home_is_the_library_async_home_and_needs_no_network(
    default_extract: ExtractConfig,
) -> None:
    source = CloudSource(ACCESS_POINT, TOKEN, 1.0, default_extract)
    module = importlib.import_module("homematicip.async_home")
    assert isinstance(source._new_home(), module.AsyncHome)  # noqa: SLF001


def test_status_mapping_with_the_real_library_exceptions() -> None:
    from homematic_exporter.source.cloud import _status_of

    errors = importlib.import_module("homematicip.exceptions.connection_exceptions")
    assert _status_of(errors.HmipAuthenticationError("x")) == 403
    assert _status_of(errors.HmipThrottlingError()) == 429
    assert _status_of(errors.HmipConnectionError("Error: 500 Internal")) == 500
    assert _status_of(errors.HmipConnectionError("no status here")) is None


async def test_secret_as_top_level_key_is_redacted_from_the_payload_error_body(
    default_extract: ExtractConfig,
) -> None:
    with pytest.raises(UpstreamError) as err:
        await make(FakeHome({TOKEN: 1}), default_extract).fetch()
    assert TOKEN not in err.value.body + str(err.value)
    assert "dict" in err.value.body
    assert err.value.__context__ is None


async def test_cancel_while_the_first_home_is_created_in_the_worker_thread(
    mini_state: dict[str, Any], default_extract: ExtractConfig
) -> None:
    import threading

    release = threading.Event()
    started = threading.Event()
    home = FakeHome(mini_state)

    def factory() -> FakeHome:
        started.set()
        release.wait(5)
        return home

    source = CloudSource(ACCESS_POINT, TOKEN, 5.0, default_extract, home_factory=factory)
    task = asyncio.create_task(source.fetch())
    assert await asyncio.to_thread(started.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    assert source._home is None  # noqa: SLF001
    assert len((await source.fetch()).devices) == 10
