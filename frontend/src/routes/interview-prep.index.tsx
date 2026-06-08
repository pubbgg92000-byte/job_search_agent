import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { interviewApi, type InterviewDashboard } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton, EmptyState, PageError } from "@/components/ui/state";

export const Route = createFileRoute("/interview-prep/")({
  component: InterviewPrepDashboardPage,
});

function difficultyTone(d: string) {
  if (d === "very_hard") return "destructive";
  if (d === "hard") return "destructive";
  if (d === "medium") return "warning";
  return "default";
}

function severityTone(s: string) {
  if (s === "high") return "destructive";
  if (s === "medium") return "warning";
  return "default";
}

function UpcomingInterviews({ data }: { data: InterviewDashboard }) {
  if (!data.upcoming_interviews.length) {
    return <EmptyState title="No interviews scheduled" description="Move an application to 'Interview Scheduled' to see it here." />;
  }
  return (
    <ul className="space-y-3">
      {data.upcoming_interviews.map((u) => (
        <li key={u.application_id}>
          <Link
            to="/applications/$applicationId"
            params={{ applicationId: String(u.application_id) }}
            className="block rounded-md border border-border p-3 hover:bg-accent"
          >
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="text-sm font-medium">{u.title || "Untitled role"}</div>
                <div className="text-xs text-muted-foreground">{u.company || "—"}</div>
              </div>
              <Badge variant="outline">{u.status.replace(/_/g, " ")}</Badge>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function RecentPlans({ data }: { data: InterviewDashboard }) {
  if (!data.recent_plans.length) {
    return <EmptyState title="No prep plans yet" description="Generate one from an application detail page." />;
  }
  return (
    <ul className="space-y-3">
      {data.recent_plans.map((p) => (
        <li key={p.id}>
          <Link
            to="/applications/$applicationId"
            params={{ applicationId: String(p.application_id) }}
            className="block rounded-md border border-border p-3 hover:bg-accent"
          >
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div>
                <div className="text-sm font-medium">Plan #{p.id}</div>
                <div className="text-xs text-muted-foreground">
                  application {p.application_id} ·{" "}
                  {p.generated_at
                    ? new Date(p.generated_at).toLocaleDateString()
                    : "—"}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={difficultyTone(p.difficulty)}>{p.difficulty.replace(/_/g, " ")}</Badge>
                <Badge variant="outline">{p.confidence_score}% confidence</Badge>
              </div>
            </div>
            {p.technical_topics.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {p.technical_topics.slice(0, 5).map((t) => (
                  <Badge key={t} variant="secondary">
                    {t}
                  </Badge>
                ))}
              </div>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function RiskAreas({ data }: { data: InterviewDashboard }) {
  if (!data.risk_areas.length) {
    return <EmptyState title="No risk areas yet" description="Generate at least one prep plan to populate this view." />;
  }
  return (
    <ul className="space-y-2">
      {data.risk_areas.map((r) => (
        <li key={r.topic} className="flex items-center justify-between text-sm">
          <span>{r.topic}</span>
          <Badge variant="outline">{r.count} plan{r.count === 1 ? "" : "s"}</Badge>
        </li>
      ))}
    </ul>
  );
}

function RecommendedTopics({ data }: { data: InterviewDashboard }) {
  if (!data.recommended_topics.length) {
    return <EmptyState title="No topic recommendations" />;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {data.recommended_topics.map((t) => (
        <Badge key={t} variant="secondary">
          {t}
        </Badge>
      ))}
    </div>
  );
}

function InterviewPrepDashboardPage() {
  const q = useQuery({
    queryKey: ["interview-prep", "dashboard"],
    queryFn: () => interviewApi.dashboard(),
  });

  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError) return <PageError message={(q.error as Error).message} />;
  const data = q.data!;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Interview Prep</h1>
        <p className="text-sm text-muted-foreground">
          Plans, weak spots, and study material across your pipeline.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Upcoming Interviews</CardTitle>
          </CardHeader>
          <CardContent>
            <UpcomingInterviews data={data} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Preparation Plans</CardTitle>
          </CardHeader>
          <CardContent>
            <RecentPlans data={data} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Risk Areas</CardTitle>
          </CardHeader>
          <CardContent>
            <RiskAreas data={data} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recommended Topics</CardTitle>
          </CardHeader>
          <CardContent>
            <RecommendedTopics data={data} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
