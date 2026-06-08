SYSTEM = """You analyze a single job description and extract structured fields.

Rules:
- Only return information present in the JD text.
- `required_skills` are skills the JD explicitly says are required, must-have, or essential.
- `preferred_skills` are nice-to-have, bonus, or "plus" skills.
- `keywords` are other technical terms, tools, methodologies, or domain words worth surfacing.
- Skills should be canonical names (e.g. "Node.js", not "nodejs" or "node js").
- Infer seniority from the title and required years of experience. Values: junior, mid, senior, lead, principal, unknown.
- Salary: extract only if explicitly mentioned. Leave currency/min/max empty otherwise.
"""

USER_TEMPLATE = """Job description text:

<jd>
{jd_text}
</jd>

Extract the structured fields via the `emit_jd_analysis` tool."""

JD_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "company": {"type": "string"},
        "location": {"type": "string"},
        "remote": {"type": "boolean"},
        "summary": {"type": "string", "description": "One sentence about the role."},
        "required_skills": {"type": "array", "items": {"type": "string"}},
        "preferred_skills": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "experience_years_min": {"type": "integer"},
        "seniority": {
            "type": "string",
            "enum": ["junior", "mid", "senior", "lead", "principal", "unknown"],
        },
        "salary_currency": {"type": "string"},
        "salary_min": {"type": "integer"},
        "salary_max": {"type": "integer"},
    },
    "required": ["title", "required_skills", "keywords", "seniority"],
}
