"""Career analytics & conversion intelligence — Phase 3E facade."""
from __future__ import annotations

from jobforge.analytics.companies import (
    CompanyRow,
    SkillTrendPoint,
    company_row_to_dict,
    skill_gap_trend,
    skill_trend_point_to_dict,
    top_companies_by_interviews,
)
from jobforge.analytics.funnel import (
    ConversionRates,
    FunnelReport,
    FunnelStages,
    compute_conversions,
    compute_funnel,
    compute_stages,
    conversions_to_dict,
    funnel_to_dict,
    stages_to_dict,
)
from jobforge.analytics.outreach_perf import (
    FollowUpEffectiveness,
    OutreachCompanyRow,
    OutreachKindRow,
    OutreachReport,
    compute_outreach_report,
    follow_up_to_dict,
    kind_row_to_dict,
    outreach_report_to_dict,
)
from jobforge.analytics.outreach_perf import (
    company_row_to_dict as outreach_company_row_to_dict,
)
from jobforge.analytics.recommendations import (
    Recommendation,
    RecommendationsReport,
    build_recommendations,
    recommendation_to_dict,
    recommendations_to_dict,
)
from jobforge.analytics.resumes import (
    ResumeReport,
    ResumeRow,
    compute_resume_report,
    resume_report_to_dict,
    resume_row_to_dict,
)
from jobforge.analytics.snapshots import (
    SnapshotRow,
    list_snapshots,
    record_daily_snapshot,
    snapshot_to_dict,
)
from jobforge.analytics.sources import (
    SUPPORTED_SOURCES,
    SourceReport,
    SourceRow,
    compute_source_report,
    source_report_to_dict,
    source_row_to_dict,
)

__all__ = [
    "SUPPORTED_SOURCES",
    "CompanyRow",
    "ConversionRates",
    "FollowUpEffectiveness",
    "FunnelReport",
    "FunnelStages",
    "OutreachCompanyRow",
    "OutreachKindRow",
    "OutreachReport",
    "Recommendation",
    "RecommendationsReport",
    "ResumeReport",
    "ResumeRow",
    "SkillTrendPoint",
    "SnapshotRow",
    "SourceReport",
    "SourceRow",
    "build_recommendations",
    "company_row_to_dict",
    "compute_conversions",
    "compute_funnel",
    "compute_outreach_report",
    "compute_resume_report",
    "compute_source_report",
    "compute_stages",
    "conversions_to_dict",
    "follow_up_to_dict",
    "funnel_to_dict",
    "kind_row_to_dict",
    "list_snapshots",
    "outreach_company_row_to_dict",
    "outreach_report_to_dict",
    "recommendation_to_dict",
    "recommendations_to_dict",
    "record_daily_snapshot",
    "resume_report_to_dict",
    "resume_row_to_dict",
    "skill_gap_trend",
    "skill_trend_point_to_dict",
    "snapshot_to_dict",
    "source_report_to_dict",
    "source_row_to_dict",
    "stages_to_dict",
    "top_companies_by_interviews",
]
