from __future__ import annotations

import json
from typing import Any

from jobforge.llm.client import call_text
from jobforge.llm.prompts.cover_letter import SYSTEM, USER_TEMPLATE


async def write_cover_letter(
    *,
    profile: dict[str, Any],
    jd: dict[str, Any],
    company_name: str | None = None,
) -> str:
    """Generate a 3-paragraph cover letter as Markdown."""
    user = USER_TEMPLATE.format(
        profile_json=json.dumps(profile, indent=2, ensure_ascii=False),
        jd_json=json.dumps(jd, indent=2, ensure_ascii=False),
        company_name=company_name or jd.get("company") or "your team",
    )
    return await call_text(system=SYSTEM, user=user, max_tokens=1024)
