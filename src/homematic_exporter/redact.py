"""Shared credential scrubbing (spec R15, section 9).

Third shared contract next to `contracts.py` and `config_models.py`: pure, no I/O, no logging.
Everything that logs or raises text from the upstream must pass it through `scrub` first.
Over-redaction of the value after a credential key is acceptable; leaking a secret is not.
Status codes and message words around a credential survive.
"""

import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"

# 24 hex characters not embedded in a longer alphanumeric run (underscore and punctuation do not
# count as part of the run, so `dev_<sgtin>` is caught).
_SGTIN = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{24}(?![0-9A-Za-z])")

_KEYS = (
    r"(?:auth[-_]?token|client[-_]?auth|authorization|access[-_]?token|api[-_]?key"
    r"|password|passwd|secret|pin|token)"
)
# key (optionally quoted with ' or ") then : or =, then a quoted value (with escapes) or an unquoted
# value optionally preceded by an auth scheme word. Repetitions are linear (no nested quantifiers).
_CREDENTIAL = re.compile(
    r"(?i)((?<![A-Za-z0-9])[\"']?" + _KEYS + r"(?![A-Za-z0-9])[\"']?\s*[:=]\s*)"
    r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'"
    r"|(?:(?:bearer|basic|digest|negotiate)\s+)?[^\s\",;}&']+)"
)
# a bearer credential with no key in front of it (e.g. a header echoed without its name)
_BEARER = re.compile(r"(?i)(?<![A-Za-z0-9])(bearer\s+)[A-Za-z0-9._~+/=-]{6,}")


def scrub(text: str, secrets: Iterable[str] = ()) -> str:
    """Return `text` with the given secrets, credential-looking values and SGTINs replaced."""
    out = text
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        out = out.replace(secret, REDACTED)
    out = _CREDENTIAL.sub(lambda m: m.group(1) + REDACTED, out)
    out = _BEARER.sub(lambda m: m.group(1) + REDACTED, out)
    return _SGTIN.sub(REDACTED, out)
