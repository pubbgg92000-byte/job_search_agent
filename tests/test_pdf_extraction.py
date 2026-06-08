from __future__ import annotations

from pathlib import Path

import pytest

from jobforge.agents.resume_parser import extract_pdf_text, parse_resume_pdf

FIXTURE = Path(__file__).parent / "fixtures" / "sample_resume.pdf"


def test_extract_pdf_text_returns_nonempty() -> None:
    text = extract_pdf_text(FIXTURE)
    assert "Rahul Sample" in text
    assert "Node.js" in text


def test_extract_pdf_text_uses_formfeed_between_pages() -> None:
    # Single-page fixture: no form feed should be present.
    text = extract_pdf_text(FIXTURE)
    assert "\f" not in text


async def test_parse_resume_pdf_raises_on_empty_pdf(tmp_path: Path) -> None:
    import fitz

    empty = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()  # blank page, no text
    doc.save(empty)
    doc.close()

    with pytest.raises(ValueError, match="No extractable text"):
        await parse_resume_pdf(empty)
