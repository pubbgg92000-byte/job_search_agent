from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_WORD_RE = re.compile(r"[a-zA-Z0-9+#./-]+")


def _normalize(token: str) -> str:
    """Lowercase + strip punctuation variants. Preserves '+', '#', '.', '-' for things like C++, C#, Node.js, vue-router."""
    return token.lower().strip(".,;:")


def _tokenize(text: str) -> set[str]:
    """Set of normalized tokens. Multi-word keywords are handled separately."""
    return {_normalize(m.group(0)) for m in _WORD_RE.finditer(text)}


def _contains_phrase(haystack_lower: str, needle: str) -> bool:
    """Check whether `needle` (which may be multi-word) appears as a substring in `haystack_lower`."""
    n = needle.lower().strip()
    if not n:
        return False
    return n in haystack_lower


def _has_keyword(resume_lower: str, resume_tokens: set[str], keyword: str) -> bool:
    """Whether the resume contains the keyword. Single-token keywords compare against the token set; multi-word ones do substring check."""
    k = keyword.strip()
    if not k:
        return False
    if " " in k or "-" in k or "/" in k:
        return _contains_phrase(resume_lower, k)
    return _normalize(k) in resume_tokens


@dataclass(frozen=True)
class ATSScore:
    score: int  # 0-100
    matched_required: list[str]
    missing_required: list[str]
    matched_preferred: list[str]
    missing_preferred: list[str]
    matched_keywords: list[str]
    missing_keywords: list[str]

    @property
    def all_missing(self) -> list[str]:
        """Combined miss list, deduplicated, in priority order."""
        seen: set[str] = set()
        out: list[str] = []
        for group in (self.missing_required, self.missing_preferred, self.missing_keywords):
            for k in group:
                if k.lower() not in seen:
                    seen.add(k.lower())
                    out.append(k)
        return out


# Weights (required matches matter most; generic keywords matter least).
_W_REQUIRED = 2.0
_W_PREFERRED = 1.0
_W_KEYWORD = 0.5


def score_resume(resume_text: str, jd_analysis: dict[str, Any]) -> ATSScore:
    """Compute a deterministic ATS-style match score for `resume_text` against `jd_analysis`.

    `jd_analysis` is expected to have `required_skills`, `preferred_skills`, and `keywords` lists.
    Returns a score 0-100 plus matched/missing breakdowns.
    """
    resume_lower = resume_text.lower()
    resume_tokens = _tokenize(resume_text)

    required = [s for s in jd_analysis.get("required_skills", []) if s]
    preferred = [s for s in jd_analysis.get("preferred_skills", []) if s]
    keywords = [s for s in jd_analysis.get("keywords", []) if s]

    matched_required = [k for k in required if _has_keyword(resume_lower, resume_tokens, k)]
    missing_required = [k for k in required if k not in matched_required]
    matched_preferred = [k for k in preferred if _has_keyword(resume_lower, resume_tokens, k)]
    missing_preferred = [k for k in preferred if k not in matched_preferred]
    matched_keywords = [k for k in keywords if _has_keyword(resume_lower, resume_tokens, k)]
    missing_keywords = [k for k in keywords if k not in matched_keywords]

    earned = (
        len(matched_required) * _W_REQUIRED
        + len(matched_preferred) * _W_PREFERRED
        + len(matched_keywords) * _W_KEYWORD
    )
    total = (
        len(required) * _W_REQUIRED
        + len(preferred) * _W_PREFERRED
        + len(keywords) * _W_KEYWORD
    )

    score = round(100 * earned / total) if total > 0 else 0

    return ATSScore(
        score=score,
        matched_required=matched_required,
        missing_required=missing_required,
        matched_preferred=matched_preferred,
        missing_preferred=missing_preferred,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
    )
