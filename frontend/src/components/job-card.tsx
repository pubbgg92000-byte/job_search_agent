import { Link } from "@tanstack/react-router";
import { Briefcase, MapPin, Wifi } from "lucide-react";
import type { Job } from "@/lib/api";
import { MatchScoreBadge } from "./match-score-badge";
import { Card, CardContent } from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";

export type JobCardProps = {
  job: Job;
  matchScore?: number;
  missingSkills?: string[];
  onSave?: (job: Job) => void;
  onApply?: (job: Job) => void;
};

export function formatSalary(j: Pick<Job, "salary_min" | "salary_max" | "salary_currency">) {
  if (j.salary_min == null && j.salary_max == null) return null;
  const c = j.salary_currency ?? "USD";
  const fmt = (n: number) =>
    n >= 1000 ? `${Math.round(n / 1000)}k` : String(n);
  if (j.salary_min != null && j.salary_max != null) {
    return `${c} ${fmt(j.salary_min)}–${fmt(j.salary_max)}`;
  }
  return `${c} ${fmt((j.salary_max ?? j.salary_min) as number)}`;
}

export function JobCard({ job, matchScore, missingSkills, onSave, onApply }: JobCardProps) {
  const salary = formatSalary(job);
  return (
    <Card data-testid="job-card" className="hover:border-primary/40 transition-colors">
      <CardContent className="p-4 sm:p-5 flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
              <Briefcase className="h-3 w-3" />
              {job.company}
            </div>
            <Link
              to="/jobs/$jobId"
              params={{ jobId: String(job.id) }}
              className="block mt-0.5 font-semibold text-base sm:text-lg hover:text-primary truncate"
            >
              {job.title}
            </Link>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {job.location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="h-3 w-3" /> {job.location}
                </span>
              )}
              {job.remote && (
                <span className="inline-flex items-center gap-1">
                  <Wifi className="h-3 w-3" /> Remote
                </span>
              )}
              {salary && <span>{salary}</span>}
              <Badge variant="outline" className="capitalize">
                {job.source}
              </Badge>
            </div>
          </div>
          {matchScore != null && <MatchScoreBadge score={matchScore} />}
        </div>

        {missingSkills && missingSkills.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            <span className="text-xs text-muted-foreground">Missing:</span>
            {missingSkills.slice(0, 6).map((s) => (
              <Badge key={s} variant="secondary" className="text-[10px]">
                {s}
              </Badge>
            ))}
            {missingSkills.length > 6 && (
              <span className="text-xs text-muted-foreground">+{missingSkills.length - 6}</span>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Button asChild variant="outline" size="sm">
            <Link to="/jobs/$jobId" params={{ jobId: String(job.id) }}>
              View
            </Link>
          </Button>
          {onSave && (
            <Button variant="secondary" size="sm" onClick={() => onSave(job)}>
              Save
            </Button>
          )}
          {onApply && (
            <Button size="sm" onClick={() => onApply(job)}>
              Apply
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
