import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import {
  api,
  type CompanySnapshot,
  type JobDetail,
  type MatchPayload,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { MatchScoreBadge } from "@/components/match-score-badge";
import { CompanyCard } from "@/components/company-card";
import { formatSalary } from "@/components/job-card";
import { Skeleton, PageError } from "@/components/ui/state";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/inputs";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/jobs/$jobId")({
  component: JobDetailPage,
});

function MatchBreakdown({ m }: { m: MatchPayload }) {
  const axes: { key: keyof MatchPayload; label: string; weight: number }[] = [
    { key: "skill_match", label: "Skills", weight: 35 },
    { key: "seniority_match", label: "Seniority", weight: 20 },
    { key: "location_match", label: "Location", weight: 15 },
    { key: "remote_match", label: "Remote", weight: 10 },
    { key: "salary_match", label: "Salary", weight: 10 },
    { key: "freshness", label: "Freshness", weight: 10 },
  ];
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Match Breakdown</CardTitle>
        <MatchScoreBadge score={m.score} />
      </CardHeader>
      <CardContent className="space-y-2">
        {axes.map((a) => {
          const v = m[a.key] as number;
          return (
            <div key={a.key} className="flex items-center gap-3 text-sm">
              <div className="w-24 text-muted-foreground">{a.label}</div>
              <div className="flex-1 h-2 rounded-full bg-muted">
                <div className="h-2 rounded-full bg-primary" style={{ width: `${v}%` }} />
              </div>
              <div className="w-12 text-right tabular-nums">{v}</div>
              <div className="w-12 text-right text-xs text-muted-foreground">{a.weight}%</div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function JobDetailPage() {
  const { jobId } = Route.useParams();
  const qc = useQueryClient();

  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.get<JobDetail>(`/jobs/${jobId}`),
  });

  const match = useQuery({
    queryKey: ["job", jobId, "match"],
    queryFn: () => api.get<MatchPayload>(`/jobs/${jobId}/match`),
    enabled: !!job.data,
    retry: false,
  });

  const company = useQuery({
    queryKey: ["company", job.data?.company],
    queryFn: () => api.get<CompanySnapshot>(`/companies/${encodeURIComponent(job.data!.company)}`),
    enabled: !!job.data?.company,
    retry: false,
  });

  const [tailorOpen, setTailorOpen] = useState(false);
  const [tailorResult, setTailorResult] = useState<null | {
    tailored_resume_md: string;
    cover_letter_md: string;
    score_before: number;
    score_after: number;
    artifact_id: number;
  }>(null);

  const tailorMutation = useMutation({
    mutationFn: async () => {
      const j = job.data!;
      // Find latest profile_id via dashboard payload — fallback to a hardcoded path.
      // The API requires profile_id. We use /dashboard's profile_present, and rely on
      // the backend's sole-user profile by fetching /jobs/{id}/match (which uses it) —
      // tailoring still needs the id, so we read profiles via match.profile_id.
      const profile_id = match.data?.profile_id;
      if (!profile_id) throw new Error("Upload a resume first");
      return api.post<{
        tailored_resume_md: string;
        cover_letter_md: string;
        score_before: number;
        score_after: number;
        artifact_id: number;
      }>("/tailor", {
        profile_id,
        jd_text: j.description,
        company_name: j.company,
        url: j.url,
      });
    },
    onSuccess: (data) => {
      setTailorResult(data);
      toast({ title: "Tailored resume ready", kind: "success" });
    },
    onError: (e) => toast({ title: "Tailor failed", description: (e as Error).message, kind: "error" }),
  });

  const createApp = useMutation({
    mutationFn: (status: string) =>
      api.post("/applications", {
        discovered_job_id: Number(jobId),
        status,
      }),
    onSuccess: () => {
      toast({ title: "Application created", kind: "success" });
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
    onError: (e) => toast({ title: "Failed", description: (e as Error).message, kind: "error" }),
  });

  if (job.isLoading) return <Skeleton className="h-64 w-full" />;
  if (job.isError) return <PageError message={(job.error as Error).message} />;
  const j = job.data!;
  const salary = formatSalary(j);

  return (
    <div className="space-y-6">
      <Link
        to="/jobs"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Back to jobs
      </Link>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">{j.company}</div>
                  <CardTitle className="text-2xl mt-1">{j.title}</CardTitle>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                    {j.location && <span>{j.location}</span>}
                    {j.remote && <Badge variant="outline">Remote</Badge>}
                    {salary && <span>{salary}</span>}
                    <Badge variant="outline">{j.source}</Badge>
                    {j.posted_at && (
                      <span>posted {new Date(j.posted_at).toLocaleDateString()}</span>
                    )}
                  </div>
                </div>
                {match.data && <MatchScoreBadge score={match.data.score} />}
              </div>
              <div className="flex flex-wrap gap-2 pt-3">
                <Button asChild variant="outline">
                  <a href={j.url} target="_blank" rel="noreferrer">
                    Open Listing <ExternalLink className="h-4 w-4" />
                  </a>
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => createApp.mutate("saved")}
                  disabled={createApp.isPending}
                >
                  Save
                </Button>
                <Button
                  onClick={() => {
                    setTailorOpen(true);
                    setTailorResult(null);
                    tailorMutation.mutate();
                  }}
                  disabled={tailorMutation.isPending}
                >
                  Generate Tailored Resume
                </Button>
                <Button
                  variant="default"
                  onClick={() => createApp.mutate("applied")}
                  disabled={createApp.isPending}
                >
                  Create Application
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <h3 className="font-semibold mb-2">Job Description</h3>
              <pre className="whitespace-pre-wrap text-sm text-foreground/90 font-sans leading-relaxed">
                {j.description}
              </pre>
            </CardContent>
          </Card>

          {match.data && (
            <>
              <MatchBreakdown m={match.data} />
              {match.data.missing_skills.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Missing Skills</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-wrap gap-1.5">
                    {match.data.missing_skills.map((s) => (
                      <Badge key={s} variant="secondary">
                        {s}
                      </Badge>
                    ))}
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>

        <div className="space-y-6">
          {match.isError && (
            <Card>
              <CardContent className="p-4 text-sm text-muted-foreground">
                Match score unavailable. Upload a resume to enable.
              </CardContent>
            </Card>
          )}
          {company.data && <CompanyCard company={company.data} />}
        </div>
      </div>

      <Dialog open={tailorOpen} onOpenChange={setTailorOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Tailored Resume</DialogTitle>
            <DialogDescription>
              ATS score: {tailorResult ? `${tailorResult.score_before} → ${tailorResult.score_after}` : "…"}
            </DialogDescription>
          </DialogHeader>
          {tailorMutation.isPending && <Skeleton className="h-72 w-full" />}
          {tailorMutation.isError && (
            <PageError message={(tailorMutation.error as Error).message} />
          )}
          {tailorResult && (
            <div className="grid gap-3 md:grid-cols-2 max-h-[60vh] overflow-auto">
              <div>
                <h4 className="text-sm font-semibold mb-2">Resume</h4>
                <Textarea
                  readOnly
                  className="h-64 font-mono text-xs"
                  value={tailorResult.tailored_resume_md}
                />
              </div>
              <div>
                <h4 className="text-sm font-semibold mb-2">Cover Letter</h4>
                <Textarea
                  readOnly
                  className="h-64 font-mono text-xs"
                  value={tailorResult.cover_letter_md}
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setTailorOpen(false)}>
              Close
            </Button>
            {tailorResult && (
              <Button
                onClick={() => {
                  const blob = new Blob([tailorResult.tailored_resume_md], {
                    type: "text/markdown",
                  });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `tailored-${tailorResult.artifact_id}.md`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
              >
                Download Resume
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
