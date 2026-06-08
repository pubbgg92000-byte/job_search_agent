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

// Phase 3B — apply-assist browser agent.
export type ApplyAssistSessionState =
  | "in_progress"
  | "ready_for_review"
  | "submitted"
  | "failed"
  | "cancelled";

export type ApplyAssistSession = {
  id: number;
  application_id: number;
  platform: "greenhouse" | "lever" | "ashby" | "unknown";
  state: ApplyAssistSessionState;
  headless: boolean;
  job_url: string;
  screenshot_paths: string[];
  screenshot_count: number;
  error_message: string | null;
  started_at: string;
  ready_for_review_at: string | null;
  completed_at: string | null;
  filled_fields: string[];
  skipped_fields: string[];
};

export type ApplyAssistEvent = {
  id: number;
  event_type: string;
  notes: string | null;
  occurred_at: string;
};

export type ApplyAssistEnvelope = {
  session: ApplyAssistSession;
  events: ApplyAssistEvent[];
  application_status?: string;
};

// Client-side ATS detection mirrors the backend `detect_platform` rules —
// used to gate the Apply Assist button on the job detail page so we don't
// offer it for URLs the backend will reject.
const _ATS_HOST_RULES: [string, ApplyAssistSession["platform"]][] = [
  ["greenhouse.io", "greenhouse"],
  ["lever.co", "lever"],
  ["ashbyhq.com", "ashby"],
];

const _ATS_HINT_RULES: [string, ApplyAssistSession["platform"]][] = [
  ["gh_jid=", "greenhouse"],
  ["lever-jobs", "lever"],
  ["ashby_jid=", "ashby"],
];

export function detectAtsPlatform(url: string | null | undefined): ApplyAssistSession["platform"] {
  if (!url) return "unknown";
  let host = "";
  let blob = "";
  try {
    const u = new URL(url);
    host = u.host.toLowerCase();
    blob = `${u.pathname} ${u.search}`.toLowerCase();
  } catch {
    return "unknown";
  }
  for (const [needle, p] of _ATS_HOST_RULES) if (host.includes(needle)) return p;
  for (const [needle, p] of _ATS_HINT_RULES) if (blob.includes(needle)) return p;
  return "unknown";
}

// Phase 3C — interview intelligence agent.

export type InterviewStage = {
  name: string;
  description: string;
  typical_duration_minutes: number;
};

export type InterviewRiskArea = {
  topic: string;
  reason: string;
  severity: "low" | "medium" | "high";
};

export type InterviewPlan = {
  id: number;
  application_id: number;
  stages: InterviewStage[];
  technical_topics: string[];
  behavioral_topics: string[];
  company_prep: string[];
  difficulty: "easy" | "medium" | "hard" | "very_hard";
  confidence_score: number;
  risk_areas: InterviewRiskArea[];
  strengths: string[];
  notes: string | null;
  generated_at: string | null;
  matched_skills?: string[];
  missing_skills?: string[];
};

export type InterviewQuestion = {
  id: number;
  plan_id: number;
  category: "technical" | "system_design" | "behavioral";
  topic: string;
  difficulty: "easy" | "medium" | "hard";
  prompt: string;
  answer_outline: string | null;
};

export type InterviewStudyBlock = {
  day_label: string;
  focus: string;
  activities: string[];
  duration_minutes: number;
};

export type InterviewStudyPlan = {
  id: number;
  plan_id: number;
  horizon_days: 1 | 3 | 7 | 14;
  total_hours: number;
  blocks: InterviewStudyBlock[];
  generated_at: string | null;
};

export type InterviewWeaknessReport = {
  strengths: string[];
  weaknesses: { skill: string; severity: "low" | "medium" | "high"; impact: number }[];
  matched_skills: string[];
  missing_skills: string[];
  risk_areas: InterviewRiskArea[];
};

export type InterviewDashboard = {
  generated_at: string;
  upcoming_interviews: {
    application_id: number;
    company: string | null;
    title: string | null;
    status: string;
    last_updated: string | null;
  }[];
  recent_plans: {
    id: number;
    application_id: number;
    difficulty: string;
    confidence_score: number;
    generated_at: string | null;
    technical_topics: string[];
  }[];
  risk_areas: { topic: string; count: number }[];
  recommended_topics: string[];
  recommended_horizon_days: 1 | 3 | 7 | 14;
};

export const interviewApi = {
  generatePlan: (applicationId: number, withLlmNotes = false) =>
    api.post<InterviewPlan>(
      `/applications/${applicationId}/interview-prep/plan`,
      { with_llm_notes: withLlmNotes },
    ),
  getLatestPlan: (applicationId: number) =>
    api.get<InterviewPlan>(`/applications/${applicationId}/interview-prep/plan`),
  listPlans: (applicationId: number) =>
    api.get<{ items: InterviewPlan[]; total: number }>(
      `/applications/${applicationId}/interview-prep/plans`,
    ),
  getWeaknesses: (applicationId: number) =>
    api.get<InterviewWeaknessReport>(
      `/applications/${applicationId}/interview-prep/weaknesses`,
    ),
  getPlan: (planId: number) => api.get<InterviewPlan>(`/interview-plans/${planId}`),
  generateQuestions: (planId: number, technical_topics?: string[]) =>
    api.post<{ items: InterviewQuestion[]; total: number }>(
      `/interview-plans/${planId}/questions`,
      technical_topics ? { technical_topics } : {},
    ),
  listQuestions: (
    planId: number,
    filters?: { category?: string; difficulty?: string },
  ) => {
    const q = new URLSearchParams();
    if (filters?.category) q.set("category", filters.category);
    if (filters?.difficulty) q.set("difficulty", filters.difficulty);
    const qs = q.toString();
    return api.get<{ items: InterviewQuestion[]; total: number }>(
      `/interview-plans/${planId}/questions${qs ? `?${qs}` : ""}`,
    );
  },
  generateStudyPlan: (planId: number, horizon_days: 1 | 3 | 7 | 14) =>
    api.post<InterviewStudyPlan>(
      `/interview-plans/${planId}/study-plan`,
      { horizon_days },
    ),
  listStudyPlans: (planId: number) =>
    api.get<{ items: InterviewStudyPlan[]; total: number }>(
      `/interview-plans/${planId}/study-plans`,
    ),
  dashboard: () => api.get<InterviewDashboard>("/interview-prep/dashboard"),
};

export const applyAssistApi = {
  start: (applicationId: number) =>
    api.post<ApplyAssistEnvelope>(
      `/applications/${applicationId}/apply-assist/start`,
      {},
    ),
  get: (applicationId: number, sessionId: number) =>
    api.get<ApplyAssistEnvelope>(
      `/applications/${applicationId}/apply-assist/sessions/${sessionId}`,
    ),
  approve: (applicationId: number, sessionId: number) =>
    api.post<ApplyAssistEnvelope>(
      `/applications/${applicationId}/apply-assist/sessions/${sessionId}/approve`,
      {},
    ),
  cancel: (applicationId: number, sessionId: number) =>
    api.post<ApplyAssistEnvelope>(
      `/applications/${applicationId}/apply-assist/sessions/${sessionId}/cancel`,
      {},
    ),
  screenshotUrl: (applicationId: number, sessionId: number, idx: number) =>
    `${BASE}/applications/${applicationId}/apply-assist/sessions/${sessionId}/screenshot/${idx}`,
};
