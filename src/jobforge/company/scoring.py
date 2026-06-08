"""Deterministic scoring + summary for `CompanyProfile`.

Both scores are computed only from known signals. If we have zero data, the
scores stay null — we never guess.
"""
from __future__ import annotations

from jobforge.company.base import CompanyEnrichmentData

# --- canonicalization tables --------------------------------------------------

_FUNDING_GROWTH = {
    "bootstrapped": 30,
    "pre_seed": 25,
    "preseed": 25,
    "seed": 40,
    "series_a": 55,
    "series-a": 55,
    "series_b": 65,
    "series-b": 65,
    "series_c": 75,
    "series-c": 75,
    "series_d": 80,
    "series-d": 80,
    "series_e_plus": 80,
    "series-e": 80,
    "growth": 80,
    "late_stage": 80,
    "public": 75,
    "ipo": 75,
    "acquired": 45,
}

# Headcount buckets → growth-score contribution.
_SIZE_GROWTH = {
    "1-10": 35,
    "11-50": 50,
    "51-200": 65,
    "201-500": 70,
    "501-1000": 70,
    "1001-5000": 65,
    "5000+": 60,
}

# Remote policy → small adjustment.
_REMOTE_ADJUST = {
    "remote_first": 5,
    "remote": 5,
    "remote-friendly": 2,
    "remote-friendly".replace("-", "_"): 2,
    "hybrid": 0,
    "office": -3,
    "office_first": -3,
}

# Risk-side: small headcount + no funding visibility = elevated risk.
_FUNDING_RISK = {
    "bootstrapped": 35,
    "pre_seed": 50,
    "preseed": 50,
    "seed": 45,
    "series_a": 30,
    "series-a": 30,
    "series_b": 22,
    "series-b": 22,
    "series_c": 18,
    "series-c": 18,
    "series_d": 15,
    "series-d": 15,
    "growth": 15,
    "late_stage": 15,
    "public": 12,
    "ipo": 12,
    "acquired": 28,
}

_SIZE_RISK = {
    "1-10": 55,
    "11-50": 40,
    "51-200": 28,
    "201-500": 20,
    "501-1000": 18,
    "1001-5000": 16,
    "5000+": 15,
}


def _norm(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower().replace(" ", "_")


def compute_growth_score(data: CompanyEnrichmentData) -> int | None:
    """Average of available growth signals. None if no signals known.

    Phase 3B: hiring velocity contributes alongside funding/headcount; a
    confirmed layoffs signal pulls the score down.
    """
    contribs: list[int] = []
    fs = _norm(data.funding_stage)
    if fs in _FUNDING_GROWTH:
        contribs.append(_FUNDING_GROWTH[fs])
    sz = _norm(data.company_size)
    if sz in _SIZE_GROWTH:
        contribs.append(_SIZE_GROWTH[sz])
    if data.hiring_velocity_score is not None:
        contribs.append(max(0, min(100, data.hiring_velocity_score)))
    if not contribs:
        return None

    base = sum(contribs) / len(contribs)
    rp = _norm(data.remote_policy)
    if rp in _REMOTE_ADJUST:
        base += _REMOTE_ADJUST[rp]
    if data.layoffs_detected is True:
        base -= 10
    return max(0, min(100, round(base)))


def compute_risk_score(data: CompanyEnrichmentData) -> int | None:
    """Average of available risk signals. None if no signals known.

    Phase 3B: explicit layoffs add a +20 uplift; near-zero hiring velocity
    adds +8. With no stage/headcount data at all, an explicit layoffs signal
    is enough on its own to surface a risk number.
    """
    contribs: list[int] = []
    fs = _norm(data.funding_stage)
    if fs in _FUNDING_RISK:
        contribs.append(_FUNDING_RISK[fs])
    sz = _norm(data.company_size)
    if sz in _SIZE_RISK:
        contribs.append(_SIZE_RISK[sz])
    if not contribs and data.layoffs_detected is not True:
        return None

    base = sum(contribs) / len(contribs) if contribs else 30.0
    if _norm(data.industry) is None:
        base += 2
    if data.layoffs_detected is True:
        base += 20
    if data.hiring_velocity_score is not None and data.hiring_velocity_score < 15:
        base += 8
    return max(0, min(100, round(base)))


def compute_confidence_score(data: CompanyEnrichmentData) -> int | None:
    """How much we trust the snapshot, 0-100. None when we have no signals.

    Weighted by (a) average signal confidence and (b) coverage across signal
    *kinds* — three distinct kinds outperform three duplicates of the same
    one. We never invent confidence we don't have.
    """
    if not data.signals:
        return None
    distinct_kinds = {s.kind for s in data.signals}
    avg_conf = sum(s.confidence for s in data.signals) / len(data.signals)
    coverage_bonus = min(25, len(distinct_kinds) * 4)
    score = avg_conf * 0.6 + coverage_bonus + 15
    return max(0, min(100, round(score)))


def compute_apply_recommendation(
    growth: int | None, risk: int | None
) -> bool | None:
    if growth is None and risk is None:
        return None
    if growth is None:
        return risk is not None and risk < 35
    if risk is None:
        return growth >= 55
    return growth >= 55 and risk < 45


def render_summary(data: CompanyEnrichmentData) -> str | None:
    """Template a one-line summary from KNOWN fields only.

    No hallucination — if we don't know a field, we omit it.
    """
    fragments: list[str] = []
    if data.industry:
        fragments.append(f"{data.industry} company")
    elif data.company_size or data.funding_stage:
        fragments.append("company")
    else:
        return None

    if data.company_size:
        fragments.append(f"({data.company_size} employees)")
    if data.funding_stage:
        fragments.append(f"at {data.funding_stage}")
    if data.remote_policy:
        fragments.append(f"with a {data.remote_policy} remote policy")

    return f"{data.name}: " + " ".join(fragments).strip(".") + "."
