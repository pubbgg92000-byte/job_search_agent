from __future__ import annotations

from jobforge.agents.ats_scorer import score_resume


def test_full_match_scores_100() -> None:
    jd = {
        "required_skills": ["Node.js", "TypeScript"],
        "preferred_skills": ["Docker"],
        "keywords": ["REST APIs"],
    }
    resume = "Built Node.js and TypeScript services. Used Docker. Designed REST APIs."
    result = score_resume(resume, jd)
    assert result.score == 100
    assert result.missing_required == []
    assert result.missing_preferred == []
    assert result.missing_keywords == []


def test_missing_required_dominates_score() -> None:
    jd = {
        "required_skills": ["Python", "Go"],
        "preferred_skills": ["Kubernetes"],
        "keywords": ["gRPC"],
    }
    resume = "Worked with Python. Familiar with Kubernetes and gRPC."
    result = score_resume(resume, jd)
    # Earned: required=1 * 2 = 2; preferred=1 * 1 = 1; keyword=1 * 0.5 = 0.5; total=3.5
    # Possible: 2*2 + 1*1 + 1*0.5 = 5.5
    # 3.5 / 5.5 ≈ 64
    assert result.score == round(100 * 3.5 / 5.5)
    assert result.missing_required == ["Go"]
    assert result.matched_required == ["Python"]


def test_no_jd_keywords_returns_zero_score() -> None:
    jd = {"required_skills": [], "preferred_skills": [], "keywords": []}
    result = score_resume("any text", jd)
    assert result.score == 0


def test_case_insensitive_matching() -> None:
    jd = {"required_skills": ["NODE.JS"], "preferred_skills": [], "keywords": []}
    resume = "I write node.js services."
    result = score_resume(resume, jd)
    assert result.score == 100
    assert result.matched_required == ["NODE.JS"]


def test_multi_word_keyword_substring_match() -> None:
    jd = {
        "required_skills": ["REST APIs"],
        "preferred_skills": [],
        "keywords": [],
    }
    resume = "Designed and shipped REST APIs at scale."
    result = score_resume(resume, jd)
    assert result.matched_required == ["REST APIs"]
    assert result.score == 100


def test_all_missing_orders_required_first_then_preferred_then_keywords() -> None:
    jd = {
        "required_skills": ["Rust"],
        "preferred_skills": ["Wasm"],
        "keywords": ["actor model"],
    }
    resume = "Nothing relevant here."
    result = score_resume(resume, jd)
    assert result.all_missing == ["Rust", "Wasm", "actor model"]
    assert result.score == 0


def test_all_missing_deduplicates() -> None:
    jd = {
        "required_skills": ["Docker"],
        "preferred_skills": ["docker"],
        "keywords": ["DOCKER"],
    }
    resume = "no containers here"
    result = score_resume(resume, jd)
    # Three buckets all reference the same concept; all_missing should dedupe
    # case-insensitively to a single entry.
    assert len(result.all_missing) == 1
