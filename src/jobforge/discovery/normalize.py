"""Shared helpers for adapters: HTML stripping, date parsing, salary inference, remote detection."""
from __future__ import annotations

import html
import re
from collections.abc import Iterable
from datetime import UTC, datetime

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_NEWLINE_RE = re.compile(r"\n\s*\n+")

# Salary like "$120,000 - $160,000", "USD 80k - 110k", "€90.000-€120.000".
# Accepts en/em dashes as separators because real-world JD text uses both.
_SALARY_RE = re.compile(
    r"""
    (?P<cur>[$€£]|USD|EUR|GBP|INR|₹)?     # optional currency
    \s*
    (?P<low>\d{4,}|\d{1,3}(?:[,.\s]\d{3})+|\d+(?:\.\d+)?k)
    \s*[-–—]\s*(?:to\s+)?
    (?P<cur2>[$€£]|USD|EUR|GBP|INR|₹)?
    \s*
    (?P<high>\d{4,}|\d{1,3}(?:[,.\s]\d{3})+|\d+(?:\.\d+)?k)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_CURRENCY_NORMAL = {
    "$": "USD",
    "USD": "USD",
    "€": "EUR",
    "EUR": "EUR",
    "£": "GBP",
    "GBP": "GBP",
    "INR": "INR",
    "₹": "INR",
}


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = _TAG_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    text = _NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    # Common variants from public APIs.
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def parse_unix_timestamp(value: int | float | str | None) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    # Heuristic: anything > 1e12 is milliseconds (year ~2286 in seconds — unrealistic).
    if ts > 1e12:
        ts = ts / 1000.0
    return datetime.fromtimestamp(ts, tz=UTC)


def _to_int(token: str) -> int | None:
    t = token.replace(",", "").replace(" ", "").replace(".", "").lower()
    multiplier = 1
    if t.endswith("k"):
        multiplier = 1000
        t = t[:-1]
    if not t.isdigit():
        return None
    return int(t) * multiplier


def infer_salary(*texts: str) -> tuple[int | None, int | None, str | None]:
    """Best-effort salary range extraction. Returns (min, max, currency) or all-None.

    We bail out on ambiguity rather than guess: a job with "salary depends on
    experience" should record nothing rather than a wrong range.
    """
    for text in texts:
        if not text:
            continue
        match = _SALARY_RE.search(text)
        if not match:
            continue
        low = _to_int(match.group("low"))
        high = _to_int(match.group("high"))
        if low is None or high is None or low > high or low < 1000:
            continue
        currency_token = match.group("cur") or match.group("cur2") or ""
        currency = _CURRENCY_NORMAL.get(currency_token.upper()) or _CURRENCY_NORMAL.get(
            currency_token
        )
        return low, high, currency
    return None, None, None


_REMOTE_KEYWORDS = ("remote", "work from home", "wfh", "anywhere", "distributed")


def detect_remote(*texts: str) -> bool:
    haystack = " ".join(t.lower() for t in texts if t)
    return any(kw in haystack for kw in _REMOTE_KEYWORDS)


def join_nonempty(parts: Iterable[str | None], sep: str = ", ") -> str:
    return sep.join(p for p in parts if p)
