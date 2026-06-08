SYSTEM = """You parse the raw text of a resume PDF into a structured profile.

Rules:
- Only extract information that is explicitly present in the text.
- Do not invent skills, dates, companies, or achievements.
- If a field is genuinely absent, omit it or leave it empty — never guess.
- Preserve original wording for bullet points (light cleanup only: fix obvious OCR breaks, join hyphenated line breaks).
- Skills should be deduplicated and normalized to canonical names (e.g. "node.js" and "Node JS" → "Node.js").
"""

USER_TEMPLATE = """Resume raw text (extracted from PDF, may have layout artifacts):

<resume>
{resume_text}
</resume>

Extract the profile via the `emit_profile` tool."""

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "location": {"type": "string"},
        "summary": {"type": "string"},
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Canonical, deduplicated skill names.",
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "title": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM or YYYY"},
                    "end_date": {"type": "string", "description": "YYYY-MM, YYYY, or 'Present'"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["company", "title", "bullets"],
            },
        },
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "stack": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name"],
            },
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "institution": {"type": "string"},
                    "degree": {"type": "string"},
                    "year": {"type": "string"},
                },
                "required": ["institution"],
            },
        },
        "certifications": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "skills", "experience"],
}
