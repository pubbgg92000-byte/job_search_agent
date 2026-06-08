import type { ApplicationEvent } from "@/lib/api";
import { cn } from "@/lib/cn";
import { Badge } from "./ui/badge";

const STATUS_LABELS: Record<string, string> = {
  saved: "Saved",
  tailored: "Tailored",
  applied: "Applied",
  interview_scheduled: "Interview Scheduled",
  interview_completed: "Interview Completed",
  offer: "Offer",
  accepted: "Accepted",
  declined: "Declined",
  rejected: "Rejected",
};

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "success" | "warning" | "outline"
> = {
  saved: "secondary",
  tailored: "secondary",
  applied: "default",
  interview_scheduled: "warning",
  interview_completed: "warning",
  offer: "success",
  accepted: "success",
  declined: "outline",
  rejected: "destructive",
};

export function statusLabel(s: string): string {
  return STATUS_LABELS[s] ?? s;
}

export function StatusBadge({ status }: { status: string }) {
  const variant = STATUS_VARIANT[status] ?? "outline";
  return (
    <Badge variant={variant} data-testid="status-badge">
      {statusLabel(status)}
    </Badge>
  );
}

function fmtDate(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function ApplicationTimeline({ events }: { events: ApplicationEvent[] }) {
  if (!events.length) {
    return (
      <div className="text-sm text-muted-foreground">No events recorded yet.</div>
    );
  }
  const sorted = [...events].sort(
    (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime(),
  );
  return (
    <ol data-testid="application-timeline" className="relative border-l border-border ml-3 space-y-5">
      {sorted.map((ev) => {
        const isUnusual = ev.event_type === "status_change_unusual";
        return (
          <li key={ev.id} className="ml-4">
            <span
              className={cn(
                "absolute -left-[6px] mt-1.5 h-3 w-3 rounded-full border-2 border-background",
                isUnusual ? "bg-warning" : "bg-primary",
              )}
            />
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={ev.to_status} />
              {ev.from_status && (
                <span className="text-xs text-muted-foreground">from {statusLabel(ev.from_status)}</span>
              )}
              {isUnusual && (
                <Badge variant="warning" className="text-[10px]">unusual</Badge>
              )}
            </div>
            <div className="text-xs text-muted-foreground mt-1">{fmtDate(ev.occurred_at)}</div>
            {ev.notes && <div className="text-sm mt-1">{ev.notes}</div>}
          </li>
        );
      })}
    </ol>
  );
}
