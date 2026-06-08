"""Unit tests for the deterministic Phase 3C heuristics.

No DB, no network. These are the building blocks of plan generation, so
the asserts here are tight — small drift would change every plan in the
system."""
from __future__ import annotations

from jobforge.interview.heuristics import (
    STAGE_BAR_RAISER,
    STAGE_BEHAVIORAL,
    STAGE_HM_SCREEN,
    STAGE_LIVE_CODING,
    STAGE_ONSITE,
    STAGE_RECRUITER,
    STAGE_SYSTEM_DESIGN,
    STAGE_TAKE_HOME,
    STAGE_TECH_PHONE,
    behavioral_topics_for,
    company_specific_prep,
    confidence_score,
    estimate_difficulty,
    extract_technical_topics,
    infer_company_class,
    infer_seniority,
    select_stages,
    stage_library,
)

# ---------------- infer_seniority ----------------


def test_infer_seniority_principal() -> None:
    assert infer_seniority("Principal Software Engineer") == "principal"


def test_infer_seniority_staff() -> None:
    assert infer_seniority("Staff Engineer, Platforms") == "staff"


def test_infer_seniority_senior() -> None:
    assert infer_seniority("Senior Backend Developer") == "senior"


def test_infer_seniority_mid_default_for_software_engineer() -> None:
    assert infer_seniority("Software Engineer") == "mid"


def test_infer_seniority_junior() -> None:
    assert infer_seniority("Junior Engineer") == "junior"


def test_infer_seniority_jr_abbreviation() -> None:
    assert infer_seniority("Jr. Backend Dev") == "junior"


def test_infer_seniority_distinguished_maps_to_principal() -> None:
    assert infer_seniority("Distinguished Engineer") == "principal"


def test_infer_seniority_blank_title_returns_mid() -> None:
    assert infer_seniority(None) == "mid"
    assert infer_seniority("") == "mid"


# ---------------- infer_company_class ----------------


def test_infer_company_class_bigtech_buckets() -> None:
    for size in ("1001-5000", "5001-10000", "10000+"):
        assert infer_company_class(size) == "bigtech"


def test_infer_company_class_mid_buckets() -> None:
    for size in ("201-500", "501-1000"):
        assert infer_company_class(size) == "mid"


def test_infer_company_class_startup_default() -> None:
    assert infer_company_class(None) == "startup"
    assert infer_company_class("11-50") == "startup"


# ---------------- select_stages ----------------


def test_select_stages_bigtech_senior_includes_system_design_and_bar_raiser() -> None:
    stages = select_stages(
        seniority="senior", company_class="bigtech", has_take_home_hint=False
    )
    names = [s.name for s in stages]
    assert STAGE_RECRUITER in names
    assert STAGE_ONSITE in names
    assert STAGE_BAR_RAISER in names
    assert STAGE_SYSTEM_DESIGN in names


def test_select_stages_bigtech_junior_skips_system_design() -> None:
    stages = select_stages(
        seniority="junior", company_class="bigtech", has_take_home_hint=False
    )
    assert STAGE_SYSTEM_DESIGN not in {s.name for s in stages}


def test_select_stages_startup_with_take_home_uses_take_home() -> None:
    stages = select_stages(
        seniority="mid", company_class="startup", has_take_home_hint=True
    )
    names = {s.name for s in stages}
    assert STAGE_TAKE_HOME in names
    assert STAGE_LIVE_CODING not in names


def test_select_stages_startup_without_take_home_uses_live_coding() -> None:
    stages = select_stages(
        seniority="mid", company_class="startup", has_take_home_hint=False
    )
    names = {s.name for s in stages}
    assert STAGE_LIVE_CODING in names
    assert STAGE_TAKE_HOME not in names


def test_select_stages_mid_company_senior_includes_system_design() -> None:
    stages = select_stages(
        seniority="senior", company_class="mid", has_take_home_hint=False
    )
    assert STAGE_SYSTEM_DESIGN in {s.name for s in stages}


def test_select_stages_dedupes_when_overlap() -> None:
    stages = select_stages(
        seniority="principal", company_class="bigtech", has_take_home_hint=True
    )
    names = [s.name for s in stages]
    assert len(names) == len(set(names))


def test_select_stages_always_starts_with_recruiter_then_hm() -> None:
    for cc in ("bigtech", "mid", "startup"):
        stages = select_stages(
            seniority="mid", company_class=cc, has_take_home_hint=False
        )
        assert stages[0].name == STAGE_RECRUITER
        assert stages[1].name == STAGE_HM_SCREEN


def test_select_stages_includes_behavioral_panel_for_all_classes() -> None:
    for cc in ("bigtech", "mid", "startup"):
        stages = select_stages(
            seniority="mid", company_class=cc, has_take_home_hint=False
        )
        assert STAGE_BEHAVIORAL in {s.name for s in stages}


def test_select_stages_tech_phone_present_for_all_classes() -> None:
    for cc in ("bigtech", "mid", "startup"):
        stages = select_stages(
            seniority="mid", company_class=cc, has_take_home_hint=False
        )
        assert STAGE_TECH_PHONE in {s.name for s in stages}


# ---------------- estimate_difficulty ----------------


def test_estimate_difficulty_easy_for_junior_startup_no_gaps() -> None:
    out = estimate_difficulty(
        seniority="junior", company_class="startup", missing_skill_count=0
    )
    assert out == "easy"


def test_estimate_difficulty_medium_for_mid_startup_one_gap() -> None:
    out = estimate_difficulty(
        seniority="mid", company_class="startup", missing_skill_count=1
    )
    assert out == "medium"


def test_estimate_difficulty_hard_for_senior_bigtech() -> None:
    out = estimate_difficulty(
        seniority="senior", company_class="bigtech", missing_skill_count=1
    )
    assert out == "hard"


def test_estimate_difficulty_very_hard_for_principal_bigtech_many_gaps() -> None:
    out = estimate_difficulty(
        seniority="principal", company_class="bigtech", missing_skill_count=5
    )
    assert out == "very_hard"


def test_estimate_difficulty_caps_missing_count_at_4() -> None:
    a = estimate_difficulty(
        seniority="staff", company_class="bigtech", missing_skill_count=4
    )
    b = estimate_difficulty(
        seniority="staff", company_class="bigtech", missing_skill_count=99
    )
    assert a == b


# ---------------- confidence_score ----------------


def test_confidence_score_all_matched_pegs_high() -> None:
    c = confidence_score(
        matched_skill_count=10, missing_skill_count=0, has_company_intel=True
    )
    assert 90 <= c <= 100


def test_confidence_score_zero_skills_returns_midband() -> None:
    c = confidence_score(
        matched_skill_count=0, missing_skill_count=0, has_company_intel=False
    )
    assert 40 <= c <= 60


def test_confidence_score_clamped_to_0_100() -> None:
    c = confidence_score(
        matched_skill_count=0, missing_skill_count=10, has_company_intel=False
    )
    assert c >= 0
    assert c <= 100


def test_confidence_score_company_intel_adds_signal() -> None:
    base = confidence_score(
        matched_skill_count=5, missing_skill_count=5, has_company_intel=False
    )
    boosted = confidence_score(
        matched_skill_count=5, missing_skill_count=5, has_company_intel=True
    )
    assert boosted > base


# ---------------- extract_technical_topics ----------------


def test_extract_topics_lists_missing_skills_first() -> None:
    out = extract_technical_topics(
        jd_text="Senior backend engineer using TypeScript and PostgreSQL.",
        missing_skills=["GraphQL", "Kafka"],
    )
    assert out[0] == "GraphQL"
    assert out[1] == "Kafka"


def test_extract_topics_includes_keywords_from_jd_text() -> None:
    out = extract_technical_topics(
        jd_text="We build a distributed system using Node.js and PostgreSQL.",
        missing_skills=[],
    )
    assert "postgresql" in out
    assert "node.js" in out


def test_extract_topics_dedupes_case_insensitive() -> None:
    out = extract_technical_topics(
        jd_text="postgres postgres postgres",
        missing_skills=["postgresql"],
    )
    lower = [t.lower() for t in out]
    assert lower.count("postgresql") == 1


def test_extract_topics_returns_empty_for_no_signal() -> None:
    out = extract_technical_topics(jd_text="", missing_skills=[])
    assert out == []


# ---------------- behavioral_topics_for ----------------


def test_behavioral_topics_for_junior_returns_baseline() -> None:
    out = behavioral_topics_for("junior")
    assert len(out) >= 4


def test_behavioral_topics_for_senior_adds_leadership_prompts() -> None:
    base = behavioral_topics_for("mid")
    senior = behavioral_topics_for("senior")
    assert len(senior) > len(base)


# ---------------- company_specific_prep ----------------


def test_company_specific_prep_includes_company_name() -> None:
    out = company_specific_prep(
        company="Anthropic",
        company_class="bigtech",
        summary="AI safety company",
        industry="AI",
        tech_stack=["Python", "TypeScript"],
    )
    joined = "\n".join(out)
    assert "Anthropic" in joined


def test_company_specific_prep_bigtech_mentions_leadership_principles() -> None:
    out = company_specific_prep(
        company="MegaCorp",
        company_class="bigtech",
        summary=None,
        industry=None,
        tech_stack=None,
    )
    assert any("leadership principles" in o.lower() or "operating values" in o.lower() for o in out)


def test_company_specific_prep_startup_prompts_founder_questions() -> None:
    out = company_specific_prep(
        company="TinyCo",
        company_class="startup",
        summary=None,
        industry=None,
        tech_stack=None,
    )
    assert any("founder" in o.lower() or "runway" in o.lower() for o in out)


def test_company_specific_prep_blank_inputs_returns_generic_block() -> None:
    out = company_specific_prep(
        company=None,
        company_class="startup",
        summary=None,
        industry=None,
        tech_stack=None,
    )
    assert len(out) >= 1


# ---------------- stage_library snapshot ----------------


def test_stage_library_returns_independent_dict() -> None:
    a = stage_library()
    b = stage_library()
    a.pop(STAGE_RECRUITER)
    assert STAGE_RECRUITER in b
