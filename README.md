# JobForge

AI-powered resume tailoring agent + job discovery + career operating system. Give it your master resume (PDF) and a job description; it returns a tailored resume + cover letter + an ATS score, and pings Telegram when done. **Phase 2B** turns it into a full career OS — application tracking, user preferences, company intelligence, skill-gap engine, a daily Telegram digest, and an architecture-only application agent ready for Phase 3 browser automation.

## Quickstart

Prereqs: macOS with Homebrew, Docker Desktop running, Python 3.11+ (`/opt/homebrew/bin/python3.11` confirmed present on this machine).

```bash
# 1. Install uv (one-time)
brew install uv

# 2. Install deps into a project venv
uv sync

# 3. Start Postgres
docker compose up -d

# 4. Configure secrets
cp .env.example .env
# edit .env: at minimum set ANTHROPIC_API_KEY

# 5. Run migrations
uv run alembic upgrade head

# 6. Tailor a resume for a job
uv run jobforge tailor \
  --resume tests/fixtures/sample_resume.pdf \
  --jd tests/fixtures/sample_jd_svelte.txt

# Outputs land in ./artifacts/<timestamp>/
#   - tailored.md
#   - cover.md
#   - report.json  (ATS score + missing keywords)
```

## Run the API server

```bash
uv run uvicorn jobforge.api.main:app --reload
```

Phase 1 endpoints:

- `POST /profile` — multipart upload of resume PDF, returns `{profile_id}`
- `POST /tailor` — JSON `{profile_id, jd_text, company_name?}`, returns the artifact
- `GET  /health`

Phase 2A endpoints:

- `POST /jobs/sync` — fan out across enabled adapters, normalize + dedupe, persist
- `GET  /jobs` — paginated job listing. Query params: `limit`, `offset`, `source`, `company`, `remote`, `sort` (`posted_at` / `company` / `first_seen_at`), `order` (`asc`/`desc`)
- `GET  /jobs/{id}` — single job detail (includes description + first/last-seen timestamps)
- `GET  /jobs/{id}/match` — score this job against the sole user's latest profile (returns all 6 axis scores)
- `GET  /jobs/top-matches?limit=10&min_score=70` — ranked listing for the sole user

Phase 2B endpoints:

- `GET/PUT /preferences` — user preferences for ranking & filtering (locations, remote_only, salary_min/max, preferred/excluded lists). The ranker reads these automatically.
- `POST /applications` — create an application (saved/tailored/applied — auto-hydrates from `discovered_job_id` when set)
- `GET  /applications` — paginated list, filter by `status`
- `GET  /applications/{id}` — application detail + immutable event log
- `PATCH /applications/{id}/status` — record a status transition; unusual transitions are logged but allowed
- `GET  /applications/stats` — cumulative funnel: applied/interviews/offers + interview_rate, offer_rate, acceptance_rate
- `GET  /companies/{name}` — cached company intelligence (growth_score, risk_score, summary, apply_recommendation; unknown fields stay null)
- `PUT  /companies/{name}/seed` — admin-style seed of raw enrichment signals, then re-score
- `GET  /skills/gaps` — top missing skills aggregated across the discovery catalogue
- `GET  /skills/plan` — 7-day and 30-day templated learning plans built from those gaps
- `GET  /dashboard` — single payload aggregating jobs/matches/applications/interviews/offers/gaps for a future frontend

Every API response now includes an `X-Request-ID` header that's echoed back if the caller supplies one. Logs are emitted as JSON to stderr and include the `request_id` field for cross-component tracing.

## Application status flow

The PRD's status machine: `saved → tailored → applied → interview_scheduled → interview_completed → offer → accepted/declined`, with `rejected` reachable from any pre-terminal state. Every status change writes a row to `application_events` so the funnel is reconstructible even when transitions skip stages (which they will — recruiters reach out, friends forward jobs, etc.). Unusual transitions (e.g. `offer → applied`) are tagged `event_type=status_change_unusual` rather than blocked.

## Telegram automation

- Daily digest at 08:00 local time via `jobforge scheduler`. The digest aggregates new jobs, top matches, application funnel, and top skill gaps; it goes to the configured `TELEGRAM_CHAT_ID`.
- Polling bot via `jobforge telegram-bot` exposes `/jobs`, `/matches`, `/applications`, `/interviews`, `/stats`, `/gaps`, `/help`.
- One-shot rendering: `jobforge digest` builds and prints the digest; `jobforge digest --send` also delivers it.
- All Telegram requests share the structured-logging + request-id machinery from Phase 1.

## Configuring discovery sources

Phase 2A reads source config from the `job_sources` table. Seed rows look like:

```sql
INSERT INTO job_sources (kind, slug, display_name, enabled, config_json) VALUES
  ('greenhouse', 'stripe',       'Stripe',       true, NULL),
  ('lever',      'netflix',      'Netflix',      true, NULL),
  ('ashby',      'ramp',         'Ramp',         true, NULL),
  ('remoteok',   NULL,           'RemoteOK',     true, NULL),
  ('remotive',   NULL,           'Remotive',     true, NULL),
  ('wwr',        NULL,           'WeWorkRemotely', true,
    '{"category": "remote-programming-jobs"}');
```

Supported `kind` values: `greenhouse`, `lever`, `ashby`, `remoteok`, `remotive`, `wwr`. Greenhouse / Lever / Ashby require a `slug` (the company's board identifier). The aggregator-style sources (RemoteOK, Remotive, WWR) ignore `slug`.

To trigger discovery:

```bash
curl -X POST http://127.0.0.1:8000/jobs/sync
```

Discovered jobs land in `discovered_jobs` (distinct from Phase 1's `jobs` table, which still holds user-submitted JDs for tailoring). Each sync gets a row in `job_sync_runs` for observability.

## Match engine

For each (profile, discovered_job) pair the engine scores six axes (0-100 each) and combines them with the PRD weights:

| Axis | Weight | What it measures |
|---|---|---|
| skill | 35% | overlap between profile skills and job-derived keywords |
| seniority | 20% | gap between inferred profile seniority and inferred job seniority |
| location | 15% | match between user's preferred locations and job location |
| remote | 10% | alignment between user's remote preference and job's remote flag |
| salary | 10% | job's top of band vs user's salary floor |
| freshness | 10% | days since `posted_at` (decay) |

Preferences for location / salary / remote are not yet exposed via API (Phase 2B); the default `UserPreferences()` prefers remote with no location or salary floor.

The matcher is fully deterministic — no LLM call — so `GET /jobs/top-matches` is fast and free.

## Telegram digest

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. Then every successful `jobforge tailor` run posts a digest to that chat.

To get your chat ID, message your bot once, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates`.

## Run the tests

```bash
uv run pytest
```

100+ deterministic tests. No live API calls — adapter tests use stored fixtures in `tests/fixtures/adapters/`; LLM-dependent tests monkeypatch the agent functions; DB-touching tests hit the live docker-compose Postgres.

## Repo layout

```
src/jobforge/
  config.py              # env-driven settings
  logging_setup.py       # JSON logging + ContextVar request IDs
  db/                    # SQLAlchemy models + async session
  llm/
    client.py            # Anthropic wrapper: retries, semaphore, cached system prompt
    prompts/             # one constant per agent
  agents/                # parser, jd_analyzer, ats_scorer, tailoring, cover_letter
  pipelines/             # tailor_for_jd: the end-to-end orchestration
  discovery/             # Phase 2A: source adapters, normalization, service
  match/                 # Phase 2A: deterministic matcher + ranking weights
  preferences/           # Phase 2B: prefs storage + match-engine adapter
  applications/          # Phase 2B: tracking service + status machine
  company/               # Phase 2B: enrichment providers + scoring + cached service
    providers/           # ManualProvider today; real APIs in Phase 3
  skills/                # Phase 2B: gap aggregation + 7d/30d learning plans
  scheduler/             # Phase 2B: in-process daily scheduler + digest runner
  telegram/              # outbound notifier + digest builder + command bot
  application_agent/     # Phase 2B: ATS detector + field mapper + ApplicationPackage
  agents_phase3/         # Phase 3 ABCs: BrowserAgent / Playwright / TelegramAgent / CompanyResearchAgent
  api/                   # FastAPI surface
    main.py              # app + RequestIdMiddleware
    routes/              # profile, tailor, jobs, preferences, applications, company, skills, dashboard
  cli.py                 # Typer entry point: tailor, ingest, scheduler, telegram-bot, digest
tests/
  fixtures/              # sample resume + JDs
    adapters/            # one JSON/XML payload per source
```

## What's deliberately *not* here yet

- No browser auto-apply or form submission — Phase 3 (`agents_phase3.PlaywrightAgent` is a stub)
- No LLM-backed company research agent — `CompanyIntelligenceService` is deterministic and refuses to invent fields
- No web frontend — Phase 3
- No auth / multi-user — Phase 3
- No pgvector / semantic match — Phase 3
- No LinkedIn / Indeed / Naukri ingestion — out of scope per PRD

