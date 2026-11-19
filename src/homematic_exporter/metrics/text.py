"""Sanitising of text that reaches the exposition or an error message.

Only categories that can break the text format, forge log lines or reorder displayed text are
replaced: control characters (Cc), lone surrogates (Cs), line/paragraph separators (Zl, Zp) and
bidi controls. Everything else (umlauts, emoji, ZWJ sequences) passes through unchanged.
"""

import re

MAX_LABEL_LENGTH = 200

_CONTROLS = re.compile("[\x00-\x1f\x7f-\x9f\ud800-\udfff  ‪-‮⁦-⁩]")
# 32+ characters of token alphabet with both a letter and a digit: looks like a credential.
_TOKEN_LIKE = re.compile(r"(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{32,}")
REDACTED = "[REDACTED]"


def clean_text(value: str, limit: int = MAX_LABEL_LENGTH) -> str:
    """Make `value` safe for a label or help text: cap, replace unsafe characters, strip."""
    return _CONTROLS.sub(" ", value[:limit]).strip()


def escape_text(value: str) -> str:
    """Show unsafe characters as escapes (`\\n`, `\\x1b`) so text cannot forge log lines."""
    return _CONTROLS.sub(lambda m: m.group().encode("unicode_escape").decode("ascii"), value)


def hide_tokens(value: str) -> str:
    return _TOKEN_LIKE.sub(REDACTED, value)
