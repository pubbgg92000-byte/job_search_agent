from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from jobforge.llm.client import call_structured
from jobforge.llm.prompts.resume_parse import PROFILE_SCHEMA, SYSTEM, USER_TEMPLATE


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract plain text from a PDF using PyMuPDF.

    Concatenates pages with form-feed separators so the LLM can see page
    boundaries if layout matters.
    """
    doc = fitz.open(pdf_path)
    try:
        pages: list[str] = []
        for page in doc:
            pages.append(page.get_text("text"))
        return "\f".join(pages).strip()
    finally:
        doc.close()


async def parse_resume(raw_text: str) -> dict[str, Any]:
    """Send raw resume text to Claude, get a structured profile dict back."""
    return await call_structured(
        system=SYSTEM,
        user=USER_TEMPLATE.format(resume_text=raw_text),
        tool_name="emit_profile",
        tool_description="Emit the structured candidate profile extracted from the resume.",
        input_schema=PROFILE_SCHEMA,
    )


async def parse_resume_pdf(pdf_path: Path) -> tuple[str, dict[str, Any]]:
    """End-to-end: PDF on disk -> (raw text, structured profile)."""
    raw_text = extract_pdf_text(pdf_path)
    if not raw_text.strip():
        raise ValueError(
            f"No extractable text in {pdf_path} — is it a scanned image without OCR?"
        )
    parsed = await parse_resume(raw_text)
    return raw_text, parsed
