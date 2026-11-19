"""Sanitising of text that reaches the exposition or an error message.

Only categories that can break the text format, forge log lines or reorder displayed text are
replaced: control characters (Cc), lone surrogates (Cs), line/paragraph separators (Zl, Zp) and
bidi controls (U+202A-202E, U+2066-2069, LRM U+200E, RLM U+200F, ALM U+061C). Everything else
(umlauts, emoji, ZWJ and ZWNJ sequences) passes through unchanged.
"""

import re

MAX_LABEL_LENGTH = 200

NAME_PATTERN = re.compile(r"^homematic_[a-z0-9]+(?:_[a-z0-9]+)+$")
_CONTROLS = re.compile(
    "[\\x00-\\x1f\\x7f-\\x9f\\ud800-\\udfff\\u2028\\u2029\\u202a-\\u202e\\u2066-\\u2069"
    "\\u200e\\u200f\\u061c]"
)
# 32+ characters of token alphabet with both a letter and a digit: looks like a credential.
_TOKEN_LIKE = re.compile(r"(?=[A-Za-z0-9_-]*\d)(?=[A-Za-z0-9_-]*[A-Za-z])[A-Za-z0-9_-]{32,}")
# The value part of an `key=value` pair in echoed text.
_ASSIGNED = re.compile(r"(?<==)[^\s'\",;\]\)]+")
REDACTED = "[REDACTED]"


def clean_text(value: str, limit: int = MAX_LABEL_LENGTH) -> str:
    """Make `value` safe for a label or help text: replace unsafe characters, strip, cap, strip.

    The input is cut first (at twice the limit) so a huge value costs bounded work.
    """
    return _CONTROLS.sub(" ", value[: limit * 2]).strip()[:limit].strip()


def escape_text(value: str) -> str:
    """Show unsafe characters as escapes (`\\n`, `\\x1b`) so text cannot forge log lines."""
    return _CONTROLS.sub(lambda m: m.group().encode("unicode_escape").decode("ascii"), value)


def _hide_token(match: re.Match[str]) -> str:
    text = match.group()
    return text if NAME_PATTERN.fullmatch(text) else REDACTED


def hide_tokens(value: str) -> str:
    """Best-effort redaction of echoed config text; a metric name is never redacted.

    Defence in depth only: it misses short, letters-only or punctuated tokens. The config file must
    not contain secrets in the first place (spec C13).
    """
    return _ASSIGNED.sub(REDACTED, _TOKEN_LIKE.sub(_hide_token, value))


def echo_text(value: str) -> str:
    """Escape unsafe characters, then redact token-like text: for anything echoed in an error."""
    return hide_tokens(escape_text(value))
