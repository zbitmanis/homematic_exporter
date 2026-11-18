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
