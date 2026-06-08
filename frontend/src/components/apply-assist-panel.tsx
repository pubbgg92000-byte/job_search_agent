import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Loader2, X } from "lucide-react";
import {
  applyAssistApi,
  type ApplyAssistEnvelope,
  type ApplyAssistSession,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "@/lib/toast";

type Props = {
  applicationId: number;
  sessionId: number | null;
  onSessionCreated: (sessionId: number) => void;
  onDismiss: () => void;
};

function stateLabel(state: ApplyAssistSession["state"]): string {
  switch (state) {
    case "in_progress":
      return "Filling form…";
    case "ready_for_review":
      return "Ready for your review";
    case "submitted":
      return "Submitted";
    case "failed":
      return "Failed";
    case "cancelled":
      return "Cancelled";
  }
}

function stateBadgeKind(state: ApplyAssistSession["state"]): "outline" | "secondary" | "default" {
  if (state === "submitted") return "default";
  if (state === "failed" || state === "cancelled") return "outline";
  return "secondary";
}

export function ApplyAssistPanel({ applicationId, sessionId, onSessionCreated, onDismiss }: Props) {
  const qc = useQueryClient();
  const [startError, setStartError] = useState<string | null>(null);

  const startMutation = useMutation({
    mutationFn: () => applyAssistApi.start(applicationId),
    onSuccess: (data) => {
      onSessionCreated(data.session.id);
      setStartError(null);
    },
    onError: (e) => setStartError((e as Error).message),
  });

  // Kick off the start call exactly once when the panel mounts without a session id.
  useEffect(() => {
    if (sessionId == null && startMutation.status === "idle") {
      startMutation.mutate();
    }
  }, [sessionId, startMutation]);

  const sessionQuery = useQuery({
    queryKey: ["apply-assist", applicationId, sessionId],
    queryFn: () => applyAssistApi.get(applicationId, sessionId!),
    enabled: sessionId != null,
    refetchInterval: (q) => {
      const data = q.state.data as ApplyAssistEnvelope | undefined;
      if (!data) return 1500;
      const terminal = ["submitted", "failed", "cancelled"];
      return terminal.includes(data.session.state) ? false : 1500;
    },
  });

  const approveMutation = useMutation({
    mutationFn: () => applyAssistApi.approve(applicationId, sessionId!),
    onSuccess: () => {
      toast({ title: "Application submitted", kind: "success" });
      qc.invalidateQueries({ queryKey: ["apply-assist", applicationId, sessionId] });
      qc.invalidateQueries({ queryKey: ["application", String(applicationId)] });
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (e) => toast({ title: "Approve failed", description: (e as Error).message, kind: "error" }),
  });

  const cancelMutation = useMutation({
    mutationFn: () => applyAssistApi.cancel(applicationId, sessionId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["apply-assist", applicationId, sessionId] });
    },
  });

  const session = sessionQuery.data?.session;
  const events = sessionQuery.data?.events ?? [];

  const screenshots = useMemo(() => {
    if (!session) return [];
    return Array.from({ length: session.screenshot_count }).map((_, idx) => ({
      idx,
      url: applyAssistApi.screenshotUrl(applicationId, session.id, idx),
    }));
  }, [applicationId, session]);

  if (startError) {
    return (
      <Card data-testid="apply-assist-error">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-destructive" /> Could not start
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">{startError}</p>
          <Button variant="outline" onClick={onDismiss}>Close</Button>
        </CardContent>
      </Card>
    );
  }

  if (sessionId == null || !session) {
    return (
      <Card data-testid="apply-assist-loading">
        <CardContent className="p-6 flex items-center gap-3">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span>Opening the application page…</span>
        </CardContent>
      </Card>
    );
  }

  const isTerminal = ["submitted", "failed", "cancelled"].includes(session.state);

  return (
    <Card data-testid="apply-assist-panel">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <div>
          <CardTitle className="text-base">Apply Assist</CardTitle>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline" className="capitalize">{session.platform}</Badge>
            <Badge variant={stateBadgeKind(session.state)} data-testid="apply-state">
              {stateLabel(session.state)}
            </Badge>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={onDismiss} aria-label="Close">
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {session.state === "in_progress" && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Filling form…
          </div>
        )}

        {session.state === "ready_for_review" && (
          <div className="space-y-2">
            <p className="text-sm">
              Review the screenshots below, then click Approve to submit the
              application on your behalf.
            </p>
            <div className="text-xs text-muted-foreground">
              Filled: {session.filled_fields.join(", ") || "(none)"}
              {session.skipped_fields.length > 0 && (
                <> · Skipped: {session.skipped_fields.join(", ")}</>
              )}
            </div>
          </div>
        )}

        {session.state === "submitted" && (
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            Submitted. Status advanced to <strong>applied</strong>.
          </div>
        )}

        {session.state === "failed" && (
          <div className="text-sm text-destructive">
            <AlertCircle className="inline h-4 w-4 mr-1" />
            {session.error_message || "Unknown failure"}
          </div>
        )}

        {session.state === "cancelled" && (
          <div className="text-sm text-muted-foreground">Session cancelled.</div>
        )}

        {screenshots.length > 0 && (
          <div className="grid grid-cols-2 gap-2" data-testid="apply-shots">
            {screenshots.map((shot) => (
              <a
                key={shot.idx}
                href={shot.url}
                target="_blank"
                rel="noreferrer"
                className="block border rounded overflow-hidden"
              >
                <img
                  src={shot.url}
                  alt={`Step ${shot.idx + 1}`}
                  className="block w-full h-auto"
                  loading="lazy"
                />
              </a>
            ))}
          </div>
        )}

        {events.length > 0 && (
          <details className="text-xs text-muted-foreground">
            <summary>Events ({events.length})</summary>
            <ul className="mt-2 space-y-0.5">
              {events.map((e) => (
                <li key={e.id}>
                  <code>{e.event_type}</code>
                  {e.notes ? ` — ${e.notes}` : ""}
                </li>
              ))}
            </ul>
          </details>
        )}

        <div className="flex items-center gap-2 pt-2">
          {session.state === "ready_for_review" && (
            <Button
              onClick={() => approveMutation.mutate()}
              disabled={approveMutation.isPending}
              data-testid="apply-approve"
            >
              {approveMutation.isPending ? "Submitting…" : "Approve & Submit"}
            </Button>
          )}
          {!isTerminal && (
            <Button
              variant="outline"
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
              data-testid="apply-cancel"
            >
              Cancel
            </Button>
          )}
          {isTerminal && (
            <Button variant="outline" onClick={onDismiss}>
              Close
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
