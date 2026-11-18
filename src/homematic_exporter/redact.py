"""Shared credential scrubbing (spec R15, section 9).

Third shared contract next to `contracts.py` and `config_models.py`: pure, no I/O, no logging.
Everything that logs or raises text from the upstream must pass it through `scrub` first.
Over-redaction is acceptable; leaking a secret is not.
"""

import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"

_SGTIN = re.compile(r"\b[0-9A-Fa-f]{24}\b")
# key[:=]value pairs for credential-like keys, optionally quoted (JSON), optionally `Bearer <value>`
_CREDENTIAL = re.compile(
    r"(?i)(\"?\b(?:authtoken|clientauth|authorization|pin|token)\b\"?\s*[:=]\s*\"?(?:bearer\s+)?)"
    r"[^\s\",;}&]+"
)


def scrub(text: str, secrets: Iterable[str] = ()) -> str:
    """Return `text` with the given secrets, credential-looking values and SGTINs replaced."""
    out = text
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        out = out.replace(secret, REDACTED)
    out = _CREDENTIAL.sub(lambda m: m.group(1) + REDACTED, out)
    return _SGTIN.sub(REDACTED, out)
