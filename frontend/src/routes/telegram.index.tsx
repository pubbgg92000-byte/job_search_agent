import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton, PageError } from "@/components/ui/state";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/telegram/")({
  component: TelegramPage,
});

type Status = {
  configured: boolean;
  chat_id: string | null;
  bot_token_present: boolean;
  last_digest: {
    generated_at: string | null;
    top_matches: number;
    jobs_discovered_24h: number;
    applications_total: number;
  };
  next_scheduled_at: string;
  scheduled_run_at_local: string;
};

function TelegramPage() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["telegram", "status"],
    queryFn: () => api.get<Status>("/telegram/status"),
  });

  const send = useMutation({
    mutationFn: () => api.post<{ sent: boolean }>("/telegram/test-digest"),
    onSuccess: (data) => {
      toast({
        title: data.sent ? "Digest sent" : "Not sent",
        description: data.sent ? "Check your Telegram chat." : "Telegram is not configured.",
        kind: data.sent ? "success" : "warning",
      });
      qc.invalidateQueries({ queryKey: ["telegram"] });
    },
    onError: (e) => toast({ title: "Send failed", description: (e as Error).message, kind: "error" }),
  });

  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError) return <PageError message={(q.error as Error).message} />;
  const s = q.data!;

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Telegram</h1>
        <p className="text-sm text-muted-foreground">
          Bot status and the daily digest schedule.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Bot Status
            {s.configured ? (
              <Badge variant="success" className="gap-1">
                <CheckCircle2 className="h-3 w-3" /> Configured
              </Badge>
            ) : (
              <Badge variant="destructive" className="gap-1">
                <XCircle className="h-3 w-3" /> Missing config
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 text-sm">
          <div>
            <div className="text-xs text-muted-foreground">Bot token</div>
            <div>{s.bot_token_present ? "Present" : "Missing — set TELEGRAM_BOT_TOKEN"}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Chat ID</div>
            <div className="font-mono">{s.chat_id ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Daily run time</div>
            <div>{s.scheduled_run_at_local}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Next scheduled</div>
            <div>{new Date(s.next_scheduled_at).toLocaleString()}</div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Last Digest Preview</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3 text-sm">
          <div>
            <div className="text-xs text-muted-foreground">Generated at</div>
            <div>
              {s.last_digest.generated_at
                ? new Date(s.last_digest.generated_at).toLocaleString()
                : "—"}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Top matches</div>
            <div>{s.last_digest.top_matches}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Jobs in 24h</div>
            <div>{s.last_digest.jobs_discovered_24h}</div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4 flex items-center justify-between gap-3 flex-wrap">
          <div className="text-sm">
            Trigger the digest now to test connectivity.
          </div>
          <Button onClick={() => send.mutate()} disabled={!s.configured || send.isPending}>
            <Send className="h-4 w-4" />
            {send.isPending ? "Sending…" : "Send Test Digest"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
