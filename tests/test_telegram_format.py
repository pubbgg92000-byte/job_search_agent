from __future__ import annotations

from pathlib import Path

from jobforge.pipelines.tailor_for_jd import TailorResult
from jobforge.telegram.notifier import _escape_markdown_v2, _format_digest


def test_escape_markdown_v2_quotes_specials() -> None:
    assert _escape_markdown_v2("a.b") == "a\\.b"
    assert _escape_markdown_v2("(x)") == "\\(x\\)"
    assert _escape_markdown_v2("100%") == "100%"  # % isn't a MarkdownV2 special


def test_format_digest_contains_score_and_company() -> None:
    result = TailorResult(
        artifact_id=1,
        profile_id=1,
        job_id=1,
        tailored_resume_md="x",
        cover_letter_md="y",
        score_before=42,
        score_after=88,
        missing_keywords=["Docker"],
        company="Acme Inc",
        title="Senior Engineer",
    )
    text = _format_digest(result, Path("/tmp/out"))
    assert "Acme Inc" in text
    assert "Senior Engineer" in text
    assert "42" in text and "88" in text
    assert "Docker" in text
