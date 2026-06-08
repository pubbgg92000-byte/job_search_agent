from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    profiles: Mapped[list[Profile]] = relationship(back_populates="user")
    jobs: Mapped[list[Job]] = relationship(back_populates="user")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_resume_text: Mapped[str] = mapped_column(Text)
    parsed_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="profiles")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="pasted")
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_jd_text: Mapped[str] = mapped_column(Text)
    parsed_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="jobs")


class TailoredArtifact(Base):
    __tablename__ = "tailored_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    tailored_resume_md: Mapped[str] = mapped_column(Text)
    cover_letter_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    ats_score: Mapped[int] = mapped_column(Integer, default=0)
    missing_keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    model_used: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Phase 1: when a tailoring pipeline run created the application, these reference
    # the user-submitted JD + the resulting artifact. Phase 2B: applications can start
    # as "Saved" with neither set, or be tied to a discovered_job instead.
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True, index=True)
    artifact_id: Mapped[int | None] = mapped_column(
        ForeignKey("tailored_artifacts.id"), nullable=True
    )
    discovered_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovered_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recruiter_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recruiter_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="saved")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------- Phase 2: job discovery ----------------


class JobSource(Base):
    """Configured ingestion source (a Greenhouse board, a Lever org, etc.)."""

    __tablename__ = "job_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("kind", "slug", name="uq_job_sources_kind_slug"),)


class DiscoveredJob(Base):
    """A job listing pulled from a source. Distinct from `jobs` (user-submitted JDs)."""

    __tablename__ = "discovered_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_job_id: Mapped[str] = mapped_column(String(255))
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_sources.id", ondelete="SET NULL"), nullable=True
    )
    company: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(512))
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(2048))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_discovered_jobs_source_id"),
    )


class JobMatch(Base):
    __tablename__ = "job_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    discovered_job_id: Mapped[int] = mapped_column(
        ForeignKey("discovered_jobs.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE")
    )
    score: Mapped[int] = mapped_column(Integer)
    skill_match: Mapped[int] = mapped_column(Integer)
    seniority_match: Mapped[int] = mapped_column(Integer)
    location_match: Mapped[int] = mapped_column(Integer)
    remote_match: Mapped[int] = mapped_column(Integer)
    salary_match: Mapped[int] = mapped_column(Integer)
    freshness: Mapped[int] = mapped_column(Integer)
    missing_skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "discovered_job_id", "profile_id",
            name="uq_job_matches_user_job_profile",
        ),
    )


class JobSyncRun(Base):
    __tablename__ = "job_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_sources.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="running")
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------- Phase 2B: career OS ----------------


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    preferred_locations: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    remote_only: Mapped[bool] = mapped_column(Boolean, default=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    preferred_roles: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    preferred_skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    excluded_companies: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    excluded_keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    website: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(32), nullable=True)
    funding_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    remote_policy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    growth_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    apply_recommendation: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    raw_signals: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    interviewer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), unique=True
    )
    base_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bonus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    equity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SkillGapSnapshot(Base):
    __tablename__ = "skill_gap_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jobs_considered: Mapped[int] = mapped_column(Integer, default=0)
    gaps_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------- Phase 3B: browser application agent ----------------


class ApplySession(Base):
    """One browser-driven attempt to submit an application.

    Multiple sessions can exist per application (re-tries). State machine is
    owned by `application_agent.browser.runner`; this table is the durable
    audit copy. The live `playwright.async_api.BrowserContext` lives in an
    in-memory registry (`application_agent.browser.session`) — only its state
    snapshots persist here.
    """

    __tablename__ = "apply_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(32), default="in_progress", index=True)
    headless: Mapped[bool] = mapped_column(Boolean, default=True)
    job_url: Mapped[str] = mapped_column(String(2048))
    screenshot_paths: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ready_for_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


# ---------------- Phase 3C: interview intelligence agent ----------------


class InterviewPlan(Base):
    """Generated preparation plan for one application's interview process.

    Stored verbatim — regenerating is cheap (LLM-free for the structural
    fields, deterministic) so we don't expose an explicit "stale" concept;
    callers re-run :func:`jobforge.interview.engine.generate_plan` when they
    want fresh output and a new row is inserted.
    """

    __tablename__ = "interview_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    technical_topics: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    behavioral_topics: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    company_prep: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    difficulty: Mapped[str] = mapped_column(String(16), default="medium")
    confidence_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_areas: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    strengths: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class InterviewQuestion(Base):
    """One generated practice question, attached to an interview plan.

    `topic` is free-form (e.g. "node-event-loop", "system-design", "behavioral").
    `category` is the broad axis (technical / behavioral / system_design).
    """

    __tablename__ = "interview_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("interview_plans.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(32), index=True)
    topic: Mapped[str] = mapped_column(String(128))
    difficulty: Mapped[str] = mapped_column(String(16), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    answer_outline: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InterviewStudyPlan(Base):
    """Time-boxed study plan tied to an interview plan.

    Horizon is one of `1`, `3`, `7`, `14` (days). Multiple horizons can be
    stored for the same plan — UI picks the right one for the upcoming
    interview date.
    """

    __tablename__ = "interview_study_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("interview_plans.id", ondelete="CASCADE"), index=True
    )
    horizon_days: Mapped[int] = mapped_column(Integer, index=True)
    blocks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    total_hours: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "plan_id", "horizon_days", name="uq_interview_study_plans_plan_horizon"
        ),
    )


# ---------------- Phase 3D: recruiter outreach agent ----------------


class RecruiterContact(Base):
    """A person we want to contact at a company.

    `kind` is one of `recruiter`, `talent_partner`, `hiring_manager`,
    `engineer`. Identity is `(company, normalized name)` so re-running
    discovery on the same company does not duplicate rows — see
    `_norm_name` in `outreach/contacts.py`.
    """

    __tablename__ = "recruiter_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    company: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32), default="recruiter", index=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="manual")
    confidence: Mapped[int] = mapped_column(Integer, default=50)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "company", "name",
            name="uq_recruiter_contacts_user_company_name",
        ),
    )


class OutreachCampaign(Base):
    """One outreach effort.

    Always tied to a contact. Optional `application_id` (when the campaign
    targets a specific role) and `interview_plan_id` (when the campaign is
    follow-up tied to a scheduled interview). Status flow lives in
    `outreach/status.py`.
    """

    __tablename__ = "outreach_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("recruiter_contacts.id", ondelete="CASCADE"), index=True
    )
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    interview_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_plans.id", ondelete="SET NULL"), nullable=True
    )
    goal: Mapped[str] = mapped_column(String(32), default="initial_outreach")
    status: Mapped[str] = mapped_column(String(32), default="drafted", index=True)
    last_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    follow_up_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RecruiterMessage(Base):
    """A drafted/sent message inside a campaign.

    `kind` matches the message-generator family (initial_outreach,
    referral_request, hiring_manager_intro, follow_up, thank_you). Messages
    are immutable once `sent_at` is set — we never edit a sent message in
    place, we add a new one.
    """

    __tablename__ = "recruiter_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("outreach_campaigns.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), index=True)
    channel: Mapped[str] = mapped_column(String(16), default="linkedin")
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    template_version: Mapped[str] = mapped_column(String(16), default="v1")
    polish_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MessageEvent(Base):
    """Immutable event log for an outreach campaign.

    `event_type` covers: drafted, sent, replied, ignored, interview, closed,
    follow_up_due, follow_up_sent. Some events reference a specific message;
    others (status changes, follow-up scheduling) reference the campaign as
    a whole.
    """

    __tablename__ = "message_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("outreach_campaigns.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("recruiter_messages.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


# ---------------- Phase 3E: career analytics ----------------


class AnalyticsSnapshot(Base):
    """Daily aggregate of the funnel for trend charts.

    One row per (user_id, snapshot_date). Rebuilt by
    :func:`jobforge.analytics.snapshots.record_daily_snapshot` (idempotent —
    re-running on the same date updates the existing row).
    """

    __tablename__ = "analytics_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    jobs_discovered: Mapped[int] = mapped_column(Integer, default=0)
    jobs_saved: Mapped[int] = mapped_column(Integer, default=0)
    applications_created: Mapped[int] = mapped_column(Integer, default=0)
    applications_submitted: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    recruiter_replies: Mapped[int] = mapped_column(Integer, default=0)
    interviews_scheduled: Mapped[int] = mapped_column(Integer, default=0)
    interviews_completed: Mapped[int] = mapped_column(Integer, default=0)
    offers_received: Mapped[int] = mapped_column(Integer, default=0)
    offers_accepted: Mapped[int] = mapped_column(Integer, default=0)
    rejections: Mapped[int] = mapped_column(Integer, default=0)
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "snapshot_date",
            name="uq_analytics_snapshots_user_date",
        ),
    )
