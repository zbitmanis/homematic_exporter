import time

import pytest

from homematic_exporter.redact import REDACTED, scrub


def test_secrets_are_replaced_longest_first() -> None:
    out = scrub("token abc123 and abc", secrets=["abc", "abc123"])
    assert "abc" not in out and out.count(REDACTED) == 2


def test_empty_secrets_are_ignored() -> None:
    assert scrub("hello", secrets=["", ""]) == "hello"


@pytest.mark.parametrize(
    "text",
    [
        "CLIENTAUTH: 9f8e7d6c5b4a",
        "authToken=9f8e7d6c5b4a",
        '{"authToken": "9f8e7d6c5b4a"}',
        "Authorization: Bearer 9f8e7d6c5b4a",
        "pin: 1234",
        "PIN=1234",
    ],
)
def test_credential_values_are_redacted(text: str) -> None:
    out = scrub(text)
    assert REDACTED in out
    assert "9f8e7d6c5b4a" not in out and "1234" not in out


def test_sgtins_are_redacted_in_any_case() -> None:
    assert scrub("device 3014F711A0000000000A1B2C failed") == f"device {REDACTED} failed"
    assert scrub("device 3014f711a0000000000a1b2c failed") == f"device {REDACTED} failed"


def test_harmless_text_is_unchanged() -> None:
    text = "poll failed: status=503 body=gateway timeout after 10 s"
    assert scrub(text) == text


def test_idempotent_and_safe_on_odd_input() -> None:
    once = scrub("authToken=abc", secrets=["abc"])
    assert scrub(once, secrets=["abc"]) == once
    assert scrub("") == ""
    assert scrub("\x00\n\t ünïcode") == "\x00\n\t ünïcode"


@pytest.mark.parametrize(
    ("text", "leak"),
    [
        ("{'authToken': 'abc123', 'status': 401}", "abc123"),
        ("{'CLIENTAUTH': 'abc123', 'x': 1}", "abc123"),
        ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ("Authorization: Digest abcdef123456", "abcdef123456"),
        ("request failed with Bearer abc123456789 rejected", "abc123456789"),
        ("Bearer abc123", "abc123"),
        ("auth_token=abc123", "abc123"),
        ("access-token: abc123", "abc123"),
        ("api_key=abc123", "abc123"),
        ("password=hunter2", "hunter2"),
        ("passwd: hunter2", "hunter2"),
        ("secret: s3cr3t", "s3cr3t"),
        ('token: "abc def"', "def"),
        ('{"token":"ab\\"cd"}', "cd"),
        ("{'password': 'it\\'s secret'}", "secret"),
        ("my_token=abc123", "abc123"),
        ("url?x=1&token=abc123&y=2", "abc123"),
        ("dev_3014F711A000000000000001 failed", "3014F711A000000000000001"),
    ],
)
def test_realistic_leak_shapes_are_redacted(text: str, leak: str) -> None:
    assert leak not in scrub(text)


def test_status_and_message_survive_redaction() -> None:
    out = scrub("status 401 message: Unauthorized token=abc123 after 3 tries")
    assert "status 401" in out and "Unauthorized" in out and "after 3 tries" in out
    body = scrub('{"status":401,"message":"bad request","authToken":"abc123"}')
    assert '"status":401' in body and '"message":"bad request"' in body


def test_prose_is_not_over_redacted() -> None:
    text = "the bearer of bad news said the pin was unavailable and a secret garden exists"
    assert scrub(text) == text


def test_large_inputs_are_fast() -> None:
    for chunk in ("token=", "a" * 50 + " ", "0123456789ABCDEF" * 4, '"\\' * 10):
        big = chunk * (100_000 // len(chunk))
        start = time.perf_counter()
        scrub(big)
        assert time.perf_counter() - start < 1.0
