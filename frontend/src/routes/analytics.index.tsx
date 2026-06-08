import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import {
  analyticsApi,
  type AnalyticsDashboard,
  type FunnelStages,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, PageError, Skeleton } from "@/components/ui/state";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/analytics/")({
  component: AnalyticsPage,
});

function pct(n: number) {
  return `${Math.round(n * 100)}%`;
}

function confidenceTone(c: string) {
  if (c === "high") return "success";
  if (c === "low") return "outline";
  return "default";
}

const FUNNEL_LABELS: { key: keyof FunnelStages; label: string }[] = [
  { key: "jobs_discovered", label: "Jobs discovered" },
  { key: "jobs_saved", label: "Jobs saved" },
  { key: "applications_created", label: "Applications created" },
  { key: "applications_submitted", label: "Applications submitted" },
  { key: "messages_sent", label: "Recruiter messages sent" },
  { key: "recruiter_replies", label: "Recruiter replies" },
  { key: "interviews_scheduled", label: "Interviews scheduled" },
  { key: "interviews_completed", label: "Interviews completed" },
  { key: "offers_received", label: "Offers received" },
  { key: "offers_accepted", label: "Offers accepted" },
];

function FunnelBars({ stages }: { stages: FunnelStages }) {
  const max = Math.max(
    1,
    ...FUNNEL_LABELS.map((f) => Number(stages[f.key] ?? 0)),
  );
  return (
    <ul className="space-y-2">
      {FUNNEL_LABELS.map((f) => {
        const value = Number(stages[f.key] ?? 0);
        const widthPct = Math.round((value / max) * 100);
        return (
          <li key={f.key}>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-muted-foreground">{f.label}</span>
              <span className="font-medium">{value}</span>
            </div>
            <div className="h-2 bg-secondary rounded-full overflow-hidden">
              <div
                className="h-2 bg-primary"
                style={{ width: `${widthPct}%` }}
                aria-hidden
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function ConversionList({ data }: { data: AnalyticsDashboard }) {
  const c = data.funnel.conversions;
  const rows = [
    { label: "Discovery → apply", v: c.discovery_to_apply },
    { label: "Apply → reply", v: c.apply_to_reply },
    { label: "Apply → interview", v: c.apply_to_interview },
    { label: "Interview → offer", v: c.interview_to_offer },
    { label: "Offer → acceptance", v: c.offer_to_acceptance },
  ];
  return (
    <ul className="space-y-2">
      {rows.map((r) => (
        <li key={r.label} className="flex items-center justify-between text-sm">
          <span>{r.label}</span>
          <Badge variant="outline">{pct(r.v)}</Badge>
        </li>
      ))}
    </ul>
  );
}

function SourceTable({ data }: { data: AnalyticsDashboard }) {
  const rows = data.sources.rows.filter((r) => r.applications > 0);
  if (!rows.length) {
    return <EmptyState title="No source data yet" />;
  }
  return (
    <table className="text-sm w-full">
      <thead>
        <tr className="text-xs text-muted-foreground">
          <th className="text-left font-normal">Source</th>
          <th className="text-right font-normal">Apps</th>
          <th className="text-right font-normal">Int.</th>
          <th className="text-right font-normal">Offers</th>
          <th className="text-right font-normal">Rate</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.source} className="border-t border-border">
            <td className="py-1">{r.source}</td>
            <td className="text-right">{r.applications}</td>
            <td className="text-right">{r.interviews}</td>
            <td className="text-right">{r.offers}</td>
            <td className="text-right">{pct(r.interview_rate)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CompaniesTable({ data }: { data: AnalyticsDashboard }) {
  const rows = data.top_companies;
  if (!rows.length) {
    return <EmptyState title="No company data yet" />;
  }
  return (
    <table className="text-sm w-full">
      <thead>
        <tr className="text-xs text-muted-foreground">
          <th className="text-left font-normal">Company</th>
          <th className="text-right font-normal">Apps</th>
          <th className="text-right font-normal">Int.</th>
          <th className="text-right font-normal">Offers</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.company} className="border-t border-border">
            <td className="py-1">{r.company}</td>
            <td className="text-right">{r.applications}</td>
            <td className="text-right">{r.interviews}</td>
            <td className="text-right">{r.offers}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ResumesTable({ data }: { data: AnalyticsDashboard }) {
  const rows = data.resumes.rows.filter((r) => r.applications > 0);
  if (!rows.length) {
    return <EmptyState title="No resume variants tracked yet" />;
  }
  return (
    <table className="text-sm w-full">
      <thead>
        <tr className="text-xs text-muted-foreground">
          <th className="text-left font-normal">Artifact</th>
          <th className="text-right font-normal">ATS</th>
          <th className="text-right font-normal">Apps</th>
          <th className="text-right font-normal">Int.</th>
          <th className="text-right font-normal">Rate</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.artifact_id} className="border-t border-border">
            <td className="py-1">#{r.artifact_id}</td>
            <td className="text-right">{r.ats_score}</td>
            <td className="text-right">{r.applications}</td>
            <td className="text-right">{r.interviews}</td>
            <td className="text-right">{pct(r.interview_rate)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SkillTrend({ data }: { data: AnalyticsDashboard }) {
  if (!data.skill_trend.length) {
    return (
      <EmptyState
        title="No skill-gap snapshots yet"
        description="Run /skills/gaps?persist=true to start tracking."
      />
    );
  }
  const latest = data.skill_trend[data.skill_trend.length - 1];
  return (
    <div className="space-y-2">
      <div className="text-xs text-muted-foreground">
        Latest snapshot · {latest.jobs_considered.toLocaleString()} jobs considered
      </div>
      <ul className="space-y-1">
        {latest.top_skills.map((s) => {
          const width = Math.min(100, s.importance_score);
          return (
            <li key={s.skill}>
              <div className="flex items-center justify-between text-xs mb-1">
                <span>{s.skill}</span>
                <span className="text-muted-foreground">
                  {s.importance_score}
                </span>
              </div>
              <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                <div
                  className="h-1.5 bg-primary"
                  style={{ width: `${width}%` }}
                  aria-hidden
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Recommendations({ data }: { data: AnalyticsDashboard }) {
  const items = data.recommendations.items;
  if (!items.length) {
    return <EmptyState title="Not enough activity for recommendations yet" />;
  }
  return (
    <ul className="space-y-3">
      {items.map((rec, i) => (
        <li key={`${rec.kind}-${i}`} className="rounded-md border border-border p-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="text-sm font-medium">{rec.title}</span>
            <Badge variant={confidenceTone(rec.confidence)}>{rec.confidence}</Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-1">{rec.detail}</p>
        </li>
      ))}
    </ul>
  );
}

function AnalyticsPage() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["analytics", "dashboard"],
    queryFn: () => analyticsApi.dashboard(),
  });
  const record = useMutation({
    mutationFn: () => analyticsApi.recordSnapshot(),
    onSuccess: () => {
      toast({ title: "Snapshot recorded", kind: "success" });
      qc.invalidateQueries({ queryKey: ["analytics", "dashboard"] });
    },
  });
  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError) return <PageError message={(q.error as Error).message} />;
  const data = q.data!;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
          <p className="text-sm text-muted-foreground">
            End-to-end funnel, conversion rates, and what's actually working.
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => record.mutate()}
          disabled={record.isPending}
        >
          {record.isPending ? "Saving…" : "Record snapshot"}
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Application Funnel</CardTitle>
          </CardHeader>
          <CardContent>
            <FunnelBars stages={data.funnel.stages} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Conversion Rates</CardTitle>
          </CardHeader>
          <CardContent>
            <ConversionList data={data} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Source Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <SourceTable data={data} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top Companies</CardTitle>
          </CardHeader>
          <CardContent>
            <CompaniesTable data={data} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Resume Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <ResumesTable data={data} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Skill Gap Trends</CardTitle>
          </CardHeader>
          <CardContent>
            <SkillTrend data={data} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Recommendations</CardTitle>
          </CardHeader>
          <CardContent>
            <Recommendations data={data} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
