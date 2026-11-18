"""Shared credential scrubbing (spec R15, section 9).

Third shared contract next to `contracts.py` and `config_models.py`: pure, no I/O, no logging.
Everything that logs or raises text from the upstream must pass it through `scrub` first.
Over-redaction of the value after a credential key is acceptable; leaking a secret is not.
Status codes and message words around a credential survive.

Known limits (pinned by tests): an unquoted credential value ends at the next whitespace, so
quote values that contain spaces; bare tokens with no key and no `Bearer` are only caught through
the `secrets=` argument; words that merely contain a credential word (`mapping`, `author`) are
left alone.
"""

import base64
import re
from collections.abc import Iterable
from urllib.parse import quote, quote_plus, unquote

REDACTED = "[REDACTED]"

# 24 hex characters not embedded in a longer alphanumeric run (underscore and punctuation do not
# count as part of the run, so `dev_<sgtin>` is caught).
_SGTIN = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{24}(?![0-9A-Za-z])")

# A key character: letter, digit, `_`, `-` or a percent-encoded byte (`auth%5Ftoken`).
_CH = r"(?:[A-Za-z0-9_-]|%[0-9A-Fa-f]{2})"
_SEP = r"(?:[:=]|%3[Dd])"
# `key` + separator, found at the start of every key (so the scan is linear). Whether the key is a
# credential is decided in code (`_is_credential_key`), not in the regex: a regex with the
# credential word inside the key (`clientAuthToken`) backtracks quadratically on long inputs.
_KEYSEP = re.compile(rf"(?<![A-Za-z0-9_%-])[\"']?(?P<key>{_CH}+)[\"']?[ \t]*{_SEP}[ \t]*")
# A quoted value (with escapes), an unterminated quote up to the end of the line, or an unquoted
# value optionally preceded by an auth scheme word.
_VALUE = re.compile(
    r"(?i)(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'"
    r"|\"[^\"\r\n]*|'[^'\r\n]*"
    r"|(?:(?:bearer|basic|digest|negotiate)\s+)?[^\s\",;}&']+)"
)
_CREDENTIAL_WORDS = (
    "token",
    "password",
    "passwd",
    "secret",
    "apikey",
    "clientauth",
    "authorization",
    "cookie",
)
# Header lines whose unquoted value is a whole credential string (Digest params, cookie lists).
_HEADER_LINE = re.compile(
    r"(?i)((?<![A-Za-z0-9_%-])(?:set-)?cookie|(?<![A-Za-z0-9_%-])authorization)"
    r"([ \t]*:[ \t]*)(?![\"'])[^\r\n]*"
)
# A bare `PIN 123456` / `PIN is 123456` in prose.
_PIN_PROSE = re.compile(r"(?i)(?<![A-Za-z0-9_])(pin\s+(?:is\s+)?)[0-9]{4,8}\b")
# A bearer credential with no key in front of it (e.g. a header echoed without its name)
_BEARER = re.compile(r"(?i)(?<![A-Za-z0-9])(bearer\s+)[A-Za-z0-9._~+/=-]{6,}")


def _is_credential_key(key: str) -> bool:
    norm = re.sub(r"[-_]", "", unquote(key).lower())
    return norm in ("pin", "pincode") or any(word in norm for word in _CREDENTIAL_WORDS)


def _redact_credentials(text: str) -> str:
    """Replace the value after every credential-looking `key:` / `key=` (single linear scan)."""
    parts: list[str] = []
    pos = 0
    while (m := _KEYSEP.search(text, pos)) is not None:
        parts.append(text[pos : m.end()])
        pos = m.end()
        if _is_credential_key(m.group("key")) and (v := _VALUE.match(text, pos)) is not None:
            parts.append(REDACTED)
            pos = v.end()
    parts.append(text[pos:])
    return "".join(parts)


def _variants(secret: str) -> set[str]:
    """The secret as it may appear in a log: raw, URL-encoded, form-encoded and base64."""
    raw = secret.encode()
    out = {secret, quote(secret, safe=""), quote_plus(secret)}
    for encoded in (base64.b64encode(raw), base64.urlsafe_b64encode(raw)):
        text = encoded.decode()
        out.update({text, text.rstrip("=")})
    return {v for v in out if v}


def scrub(text: str, secrets: Iterable[str] = ()) -> str:
    """Return `text` with the given secrets, credential-looking values and SGTINs replaced."""
    out = text
    variants = sorted({v for s in secrets if s for v in _variants(s)}, key=len, reverse=True)
    if variants:  # case-insensitive on purpose: over-redacting is fine
        out = re.sub("|".join(re.escape(v) for v in variants), REDACTED, out, flags=re.IGNORECASE)
    out = _HEADER_LINE.sub(lambda m: m.group(1) + m.group(2) + REDACTED, out)
    out = _redact_credentials(out)
    out = _PIN_PROSE.sub(lambda m: m.group(1) + REDACTED, out)
    out = _BEARER.sub(lambda m: m.group(1) + REDACTED, out)
    return _SGTIN.sub(REDACTED, out)
