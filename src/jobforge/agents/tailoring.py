from __future__ import annotations

import json
from typing import Any

from jobforge.config import get_settings
from jobforge.llm.client import call_text
from jobforge.llm.prompts.resume_tailoring import SYSTEM, USER_TEMPLATE


async def tailor_resume(
    *,
    profile: dict[str, Any],
    jd: dict[str, Any],
    missing_keywords: list[str],
) -> str:
    """Generate a tailored Markdown resume."""
    settings = get_settings()
    user = USER_TEMPLATE.format(
        profile_json=json.dumps(profile, indent=2, ensure_ascii=False),
        jd_json=json.dumps(jd, indent=2, ensure_ascii=False),
        missing_keywords=", ".join(missing_keywords) if missing_keywords else "(none)",
    )
    return await call_text(
        system=SYSTEM,
        user=user,
        model=settings.model_tailoring,
        max_tokens=4096,
    )
