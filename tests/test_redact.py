import time

import pytest

from homematic_exporter.redact import REDACTED, scrub


def test_secrets_are_replaced_longest_first() -> None:
    assert (
        scrub("see abc123 and abc", secrets=["abc", "abc123"]) == f"see {REDACTED} and {REDACTED}"
    )


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


LEAK_SHAPES = [
    "{'authToken': 'abc123'}",
    "Authorization: Basic dXNlcjpwYXNz",
    "token=abc123 pin=1234",
    "{'clientAuthToken': 'abc123'}",
    "Cookie: session=abc123; other=1",
]


def test_idempotent_on_every_leak_shape_and_safe_on_odd_input() -> None:
    for text in LEAK_SHAPES:
        once = scrub(text)
        assert scrub(once) == once, text
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


@pytest.mark.parametrize(
    ("text", "leak"),
    [
        ("{'clientAuthToken': 'abc123'}", "abc123"),
        ('{"clientAuthToken":"abc123"}', "abc123"),
        ("clientAuthToken=abc123", "abc123"),
        ("userPassword=abc123", "abc123"),
        ("{'password_hash':'abc123'}", "abc123"),
        ("secret_key=abc123", "abc123"),
        ("x-client-auth-token: abc123", "abc123"),
        ("url?token%3Dabc123&x=1", "abc123"),
        ("auth%5Ftoken%3Dabc123", "abc123"),
        ("auth%5Ftoken=abc123", "abc123"),
        ("Cookie: session=abc123; other=xyz789", "xyz789"),
        ("Set-Cookie: sid=abc123; Path=/; HttpOnly", "abc123"),
        ("headers={'cookie': 'a=abc123'}", "abc123"),
        ('Authorization: Digest username="bob", response="abc123"', "bob"),
        ('token = "unterminated abc123', "abc123"),
        ("{'password': 'unterminated abc123", "abc123"),
        ("PIN 123456", "123456"),
        ("the PIN is 123456 and wrong", "123456"),
    ],
)
def test_second_round_leak_shapes_are_redacted(text: str, leak: str) -> None:
    assert leak not in scrub(text)


@pytest.mark.parametrize(
    ("secret", "text"),
    [
        ("s3cr3t!", "GET /x?k=s3cr3t%21"),
        ("a b+c/d", "GET /x?k=a+b%2Bc%2Fd"),
        ("a b+c/d", "GET /x?k=a%20b%2Bc%2Fd"),
        ("s3cr3t", "value S3CR3T here"),
        ("s3cr3t-token", "b64 czNjcjN0LXRva2Vu"),
    ],
)
def test_secrets_argument_also_catches_encoded_and_case_variants(secret: str, text: str) -> None:
    out = scrub(text, secrets=[secret])
    assert REDACTED in out


def test_known_limits_are_pinned() -> None:
    # An unquoted credential value ends at whitespace: quote values that contain spaces.
    assert scrub("token: abc def") == f"token: {REDACTED} def"
    # Words that merely contain a credential word as part of another word are left alone.
    assert (
        scrub("mapping: ok, spinning: yes, author=bob") == "mapping: ok, spinning: yes, author=bob"
    )


@pytest.mark.parametrize("chunk", ["a-", "token", "%41", "x_", "pin ", "Token=", "'\\", "a=b;"])
def test_pathological_inputs_stay_fast(chunk: str) -> None:
    big = chunk * (100_000 // len(chunk))
    start = time.perf_counter()
    scrub(big, secrets=["abc", "s3cr3t!"])
    assert time.perf_counter() - start < 2.0


@pytest.mark.parametrize(
    ("text", "leak"),
    [
        ("private_key=abc123", "abc123"),
        ("access_key: abc123", "abc123"),
        ("sessionid=abc123", "abc123"),
        ("passphrase=abc123", "abc123"),
        ("credentials=abc123", "abc123"),
    ],
)
def test_more_credential_key_names_are_redacted(text: str, leak: str) -> None:
    assert leak not in scrub(text)


def test_documented_over_redaction_and_unrecognised_keys_are_pinned() -> None:
    for over in ("tokenizer=bpe", "secretary=bob", "cookie_policy=strict", "passwordless=true"):
        assert REDACTED in scrub(over)  # over-redaction is accepted
    assert scrub("api key=abc") == "api key=abc"  # a key with a space is not recognised
    assert scrub("key=abc") == "key=abc"


def test_a_few_secrets_on_a_large_text_stay_fast() -> None:
    big = "A" * 1_000_000
    start = time.perf_counter()
    scrub(big, secrets=["s3cr3t!", "3014F711A0000000000A1B2C", "tok"])
    assert time.perf_counter() - start < 2.0
