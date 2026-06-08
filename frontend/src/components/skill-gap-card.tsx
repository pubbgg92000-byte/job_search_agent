import type { SkillGap } from "@/lib/api";
import { Card, CardContent } from "./ui/card";

export function SkillGapCard({ gap }: { gap: SkillGap }) {
  const importance = Math.min(100, Math.round(gap.importance_score));
  return (
    <Card data-testid="skill-gap-card">
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="font-medium">{gap.skill}</div>
          <div className="text-xs text-muted-foreground">{gap.frequency} job{gap.frequency === 1 ? "" : "s"}</div>
        </div>
        <div className="mt-3 h-1.5 w-full rounded-full bg-muted">
          <div
            className="h-1.5 rounded-full bg-primary"
            style={{ width: `${importance}%` }}
            aria-label={`Importance ${importance}`}
          />
        </div>
        <div className="mt-1 text-[11px] text-muted-foreground">Importance {importance}</div>
      </CardContent>
    </Card>
  );
}
