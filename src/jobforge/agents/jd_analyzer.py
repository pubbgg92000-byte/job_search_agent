from __future__ import annotations

from typing import Any

from jobforge.llm.client import call_structured
from jobforge.llm.prompts.jd_analyzer import JD_SCHEMA, SYSTEM, USER_TEMPLATE


async def analyze_jd(jd_text: str) -> dict[str, Any]:
    """Send raw JD text to Claude, get a structured JD dict back."""
    return await call_structured(
        system=SYSTEM,
        user=USER_TEMPLATE.format(jd_text=jd_text),
        tool_name="emit_jd_analysis",
        tool_description="Emit the structured job-description analysis.",
        input_schema=JD_SCHEMA,
    )
