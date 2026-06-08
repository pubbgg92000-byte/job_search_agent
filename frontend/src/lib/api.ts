// Generated API helpers. Keeps a tiny typed surface over fetch and uses
// the Vite dev-proxy at /api, so we don't bake the backend host into builds.

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  detail?: unknown;
  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text().catch(() => undefined);
    }
    const msg =
      (detail && typeof detail === "object" && "detail" in detail
        ? String((detail as Record<string, unknown>).detail)
        : `HTTP ${res.status}`) || `HTTP ${res.status}`;
    throw new ApiError(msg, res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: async <T>(path: string, init?: RequestInit) =>
    handle<T>(await fetch(`${BASE}${path}`, { ...init, method: "GET" })),
  post: async <T>(path: string, body?: unknown, init?: RequestInit) =>
    handle<T>(
      await fetch(`${BASE}${path}`, {
        ...init,
        method: "POST",
        headers: { "content-type": "application/json", ...(init?.headers || {}) },
        body: body === undefined ? undefined : JSON.stringify(body),
      }),
    ),
  put: async <T>(path: string, body?: unknown, init?: RequestInit) =>
    handle<T>(
      await fetch(`${BASE}${path}`, {
        ...init,
        method: "PUT",
        headers: { "content-type": "application/json", ...(init?.headers || {}) },
        body: body === undefined ? undefined : JSON.stringify(body),
      }),
    ),
  patch: async <T>(path: string, body?: unknown, init?: RequestInit) =>
    handle<T>(
      await fetch(`${BASE}${path}`, {
        ...init,
        method: "PATCH",
        headers: { "content-type": "application/json", ...(init?.headers || {}) },
        body: body === undefined ? undefined : JSON.stringify(body),
      }),
    ),
  postForm: async <T>(path: string, form: FormData) =>
    handle<T>(await fetch(`${BASE}${path}`, { method: "POST", body: form })),
};

// --- typed API surface ----------------------------------------------------

export type DashboardPayload = {
  jobs_found: number;
  jobs_found_24h: number;
  high_matches: number;
  applications: number;
  applications_by_status: Record<string, number>;
  interviews: number;
  offers: number;
  rejections: number;
  interview_rate: number;
  offer_rate: number;
  skill_gaps: { skill: string; frequency: number; importance_score: number }[];
  latest_sync: {
    source: string;
    status: string;
    started_at: string;
    finished_at: string | null;
    discovered: number;
    inserted: number;
    updated: number;
  } | null;
  profile_present: boolean;
};

export type Job = {
  id: number;
  source: string;
  source_job_id: string;
  company: string;
  title: string;
  location: string | null;
  remote: boolean;
  url: string;
  posted_at: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
};

export type JobDetail = Job & {
  description: string;
  first_seen_at: string;
  last_seen_at: string;
};

export type JobList = {
  total: number;
  limit: number;
  offset: number;
  items: Job[];
};

export type MatchPayload = {
  job_id: number;
  profile_id: number;
  score: number;
  skill_match: number;
  seniority_match: number;
  location_match: number;
  remote_match: number;
  salary_match: number;
  freshness: number;
  missing_skills: string[];
};

export type TopMatch = { job: Job; match: MatchPayload };

export type Application = {
  id: number;
  user_id: number;
  company: string | null;
  title: string | null;
  url: string | null;
  source: string | null;
  status: string;
  created_at: string;
  last_updated: string;
  discovered_job_id: number | null;
  artifact_id: number | null;
  job_id: number | null;
  recruiter_name: string | null;
  recruiter_email: string | null;
  notes: string | null;
};

export type ApplicationEvent = {
  id: number;
  application_id: number;
  from_status: string | null;
  to_status: string;
  event_type: string;
  occurred_at: string;
  notes: string | null;
};

export type ApplicationDetail = Application & { events: ApplicationEvent[] };

export type ApplicationList = {
  total: number;
  limit: number;
  offset: number;
  items: Application[];
};

export type ApplicationStats = {
  total: number;
  by_status: Record<string, number>;
  applied: number;
  interviews: number;
  offers: number;
  rejections: number;
  acceptances: number;
  interview_rate: number;
  offer_rate: number;
  acceptance_rate: number;
};

export type Preferences = {
  preferred_locations: string[];
  remote_only: boolean;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  preferred_roles: string[];
  preferred_skills: string[];
  excluded_companies: string[];
  excluded_keywords: string[];
};

export type NewsItem = {
  title: string;
  summary: string;
  url: string | null;
  published_at: string | null;
  category: "funding" | "growth" | "layoffs" | "news";
};

export type CompanySignalDict = {
  kind: string;
  value: unknown;
  source: string;
  confidence: number;
  notes?: string | null;
  observed_at?: string | null;
};

export type CompanySnapshot = {
  // Phase 2B (unchanged)
  name: string;
  website: string | null;
  industry: string | null;
  company_size: string | null;
  funding_stage: string | null;
  remote_policy: string | null;
  growth_score: number | null;
  risk_score: number | null;
  summary: string | null;
  apply_recommendation: boolean | null;
  last_updated_at: string | null;
  // Phase 3B (additive — older fields untouched)
  confidence_score?: number | null;
  hiring_velocity_score?: number | null;
  open_roles_count?: number | null;
  tech_stack?: string[];
  layoffs_detected?: boolean | null;
  news_items?: NewsItem[];
  engineering_team_signals?: Record<string, unknown> | null;
  glassdoor_signals?: Record<string, unknown> | null;
  signals?: CompanySignalDict[];
};

export type SkillGap = {
  skill: string;
  frequency: number;
  importance_score: number;
};

export type SkillGapReport = {
  jobs_considered: number;
  total_jobs_examined?: number;
  top_gaps: SkillGap[];
  generated_at?: string;
};

export type LearningPlanItem = {
  skill: string;
  goal: string;
  resources: string[];
};

export type LearningPlan = {
  horizon_days: number;
  items: LearningPlanItem[];
};

export type SkillPlanResponse = {
  report: SkillGapReport;
  seven_day_plan: LearningPlan;
  thirty_day_plan: LearningPlan;
};
