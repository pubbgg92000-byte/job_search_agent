import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  TrendingUp,
  ListChecks,
  Calendar,
  Trophy,
} from "lucide-react";
import { api, type DashboardPayload, type TopMatch, type ApplicationList } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { JobCard } from "@/components/job-card";
import { SkillGapCard } from "@/components/skill-gap-card";
import { StatusBadge } from "@/components/application-timeline";
import { Skeleton, EmptyState, PageError } from "@/components/ui/state";

export const Route = createFileRoute("/")({
  component: DashboardPage,
});

type StatProps = {
  label: string;
  value: number | string;
  icon: React.ElementType;
  hint?: string;
};

function StatCard({ label, value, icon: Icon, hint }: StatProps) {
  return (
    <Card data-testid="stat-card">
      <CardContent className="p-4 sm:p-5 flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className="mt-1 text-3xl font-bold tabular-nums">{value}</div>
          {hint && <div className="text-xs text-muted-foreground mt-0.5">{hint}</div>}
        </div>
        <div className="h-9 w-9 rounded-md bg-primary/10 text-primary flex items-center justify-center">
          <Icon className="h-4 w-4" />
        </div>
      </CardContent>
    </Card>
  );
}

function DashboardPage() {
  const dash = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardPayload>("/dashboard"),
  });
  const topMatches = useQuery({
    queryKey: ["jobs", "top-matches", { limit: 5 }],
    queryFn: () => api.get<TopMatch[]>("/jobs/top-matches?limit=5"),
    retry: false,
  });
  const recentApps = useQuery({
    queryKey: ["applications", "recent"],
    queryFn: () => api.get<ApplicationList>("/applications?limit=5"),
  });

  if (dash.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    );
  }
  if (dash.isError) return <PageError message={(dash.error as Error).message} />;
  const d = dash.data!;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          {d.profile_present
            ? "Your job hunt at a glance."
            : "No profile uploaded yet. Head to Resume to get started."}
        </p>
      </div>

      <div className="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard
          label="Jobs Found"
          value={d.jobs_found}
          icon={Briefcase}
          hint={d.jobs_found_24h > 0 ? `+${d.jobs_found_24h} in 24h` : undefined}
        />
        <StatCard label="High Matches" value={d.high_matches} icon={TrendingUp} hint="score ≥ 75" />
        <StatCard label="Applications" value={d.applications} icon={ListChecks} />
        <StatCard label="Interviews" value={d.interviews} icon={Calendar} />
        <StatCard label="Offers" value={d.offers} icon={Trophy} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Top Matches</CardTitle>
            <Link to="/jobs" className="text-xs text-primary hover:underline">
              View all →
            </Link>
          </CardHeader>
          <CardContent className="space-y-3">
            {topMatches.isLoading && <Skeleton className="h-24 w-full" />}
            {topMatches.isError && (
              <EmptyState
                title="No matches available"
                description="Upload a resume to enable matching."
              />
            )}
            {topMatches.data && topMatches.data.length === 0 && (
              <EmptyState title="No matches yet" description="Run a job sync to discover postings." />
            )}
            {topMatches.data?.map((tm) => (
              <JobCard
                key={tm.job.id}
                job={tm.job}
                matchScore={tm.match.score}
                missingSkills={tm.match.missing_skills}
              />
            ))}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Recent Applications</CardTitle>
              <Link to="/applications" className="text-xs text-primary hover:underline">
                View all →
              </Link>
            </CardHeader>
            <CardContent>
              {recentApps.isLoading && <Skeleton className="h-16 w-full" />}
              {recentApps.data && recentApps.data.items.length === 0 && (
                <EmptyState title="No applications yet" />
              )}
              <ul className="divide-y divide-border">
                {recentApps.data?.items.map((a) => (
                  <li key={a.id} className="py-2 first:pt-0 last:pb-0">
                    <Link
                      to="/applications/$applicationId"
                      params={{ applicationId: String(a.id) }}
                      className="flex items-center justify-between gap-2 hover:text-primary"
                    >
                      <div className="min-w-0">
                        <div className="text-sm font-medium truncate">{a.title || "Untitled"}</div>
                        <div className="text-xs text-muted-foreground truncate">{a.company || "—"}</div>
                      </div>
                      <StatusBadge status={a.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Skill Gaps</CardTitle>
              <Link to="/skill-gaps" className="text-xs text-primary hover:underline">
                Plan →
              </Link>
            </CardHeader>
            <CardContent className="space-y-3">
              {d.skill_gaps.length === 0 ? (
                <EmptyState title="No gaps identified" />
              ) : (
                d.skill_gaps
                  .slice(0, 5)
                  .map((g) => <SkillGapCard key={g.skill} gap={g} />)
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
