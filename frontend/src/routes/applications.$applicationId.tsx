import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api, type ApplicationDetail } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { ChevronDown } from "lucide-react";
import { ApplicationTimeline, statusLabel, StatusBadge } from "@/components/application-timeline";
import { InterviewPrepPanel } from "@/components/interview-prep-panel";
import { OutreachPanel } from "@/components/outreach-panel";
import { Skeleton, PageError } from "@/components/ui/state";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/applications/$applicationId")({
  component: ApplicationDetailPage,
});

const STATUSES = [
  "saved",
  "tailored",
  "applied",
  "interview_scheduled",
  "interview_completed",
  "offer",
  "accepted",
  "declined",
  "rejected",
];

function ApplicationDetailPage() {
  const { applicationId } = Route.useParams();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["application", applicationId],
    queryFn: () => api.get<ApplicationDetail>(`/applications/${applicationId}`),
  });

  const updateStatus = useMutation({
    mutationFn: (status: string) =>
      api.patch(`/applications/${applicationId}/status`, { status }),
    onSuccess: () => {
      toast({ title: "Status updated", kind: "success" });
      qc.invalidateQueries({ queryKey: ["application", applicationId] });
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => toast({ title: "Failed", description: (e as Error).message, kind: "error" }),
  });

  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError) return <PageError message={(q.error as Error).message} />;
  const a = q.data!;

  return (
    <div className="space-y-6">
      <Link
        to="/applications"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Back to applications
      </Link>

      <Card>
        <CardHeader>
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                {a.company || "—"}
              </div>
              <CardTitle className="text-2xl mt-1">{a.title || "Untitled"}</CardTitle>
              <div className="mt-2 flex items-center gap-2">
                <StatusBadge status={a.status} />
                <span className="text-xs text-muted-foreground">
                  created {new Date(a.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button>
                  Update Status <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {STATUSES.map((s) => (
                  <DropdownMenuItem key={s} onSelect={() => updateStatus.mutate(s)}>
                    {statusLabel(s)}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {a.url && (
            <div>
              <div className="text-xs text-muted-foreground">Job URL</div>
              <a
                href={a.url}
                className="text-sm text-primary hover:underline break-all"
                target="_blank"
                rel="noreferrer"
              >
                {a.url}
              </a>
            </div>
          )}
          {a.source && (
            <div>
              <div className="text-xs text-muted-foreground">Source</div>
              <div className="text-sm">{a.source}</div>
            </div>
          )}
          {a.recruiter_name && (
            <div>
              <div className="text-xs text-muted-foreground">Recruiter</div>
              <div className="text-sm">
                {a.recruiter_name}
                {a.recruiter_email && ` · ${a.recruiter_email}`}
              </div>
            </div>
          )}
          {a.notes && (
            <div className="sm:col-span-2">
              <div className="text-xs text-muted-foreground">Notes</div>
              <div className="text-sm whitespace-pre-wrap">{a.notes}</div>
            </div>
          )}
        </CardContent>
      </Card>

      <InterviewPrepPanel applicationId={Number(applicationId)} />

      <OutreachPanel applicationId={Number(applicationId)} company={a.company} />

      <Card>
        <CardHeader>
          <CardTitle>Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <ApplicationTimeline events={a.events} />
        </CardContent>
      </Card>
    </div>
  );
}
