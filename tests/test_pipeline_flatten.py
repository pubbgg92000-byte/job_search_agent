from __future__ import annotations

from jobforge.pipelines.tailor_for_jd import _profile_to_plain_text


def test_profile_flatten_includes_summary_skills_and_experience_bullets() -> None:
    profile = {
        "summary": "Builds backend services.",
        "skills": ["Python", "Go"],
        "experience": [
            {
                "company": "Acme",
                "title": "SWE",
                "bullets": ["Shipped X", "Reduced Y by 30%"],
            }
        ],
        "projects": [
            {"name": "Forge", "description": "CLI tool", "stack": ["Rust", "WASM"]}
        ],
        "education": [{"institution": "IIT Madras", "degree": "B.Tech CS"}],
        "certifications": ["AWS SAA"],
    }
    text = _profile_to_plain_text(profile)
    assert "Builds backend services." in text
    assert "Python" in text and "Go" in text
    assert "Acme" in text and "SWE" in text
    assert "Shipped X" in text and "Reduced Y by 30%" in text
    assert "Forge" in text and "Rust" in text
    assert "IIT Madras" in text
    assert "AWS SAA" in text


def test_profile_flatten_skips_empty_fields() -> None:
    profile = {
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
    }
    text = _profile_to_plain_text(profile)
    assert text == ""


def test_profile_flatten_tolerates_missing_keys_in_jobs() -> None:
    # An experience entry with only a title; no company or bullets should not blow up.
    profile = {
        "experience": [{"title": "Founder"}],
    }
    text = _profile_to_plain_text(profile)
    assert "Founder" in text
