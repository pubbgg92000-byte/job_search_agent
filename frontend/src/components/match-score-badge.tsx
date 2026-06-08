import { cn } from "@/lib/cn";

export function scoreBucket(score: number): "high" | "mid" | "low" {
  if (score >= 75) return "high";
  if (score >= 50) return "mid";
  return "low";
}

export function MatchScoreBadge({
  score,
  size = "md",
  className,
}: {
  score: number;
  size?: "sm" | "md";
  className?: string;
}) {
  const bucket = scoreBucket(score);
  const palette = {
    high: "bg-success/15 text-success border-success/40",
    mid: "bg-warning/15 text-warning border-warning/40",
    low: "bg-muted text-muted-foreground border-border",
  }[bucket];
  return (
    <span
      data-testid="match-score-badge"
      data-bucket={bucket}
      className={cn(
        "inline-flex items-center rounded-full border font-semibold",
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
        palette,
        className,
      )}
    >
      {score}
    </span>
  );
}
