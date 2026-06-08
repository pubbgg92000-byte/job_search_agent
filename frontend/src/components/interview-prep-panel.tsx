import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GraduationCap, Sparkles } from "lucide-react";
import {
  interviewApi,
  type InterviewPlan,
  type InterviewQuestion,
  type InterviewStudyPlan,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton, EmptyState } from "@/components/ui/state";
import { toast } from "@/lib/toast";

function difficultyTone(d: string) {
  if (d === "very_hard" || d === "hard") return "destructive";
  if (d === "medium") return "warning";
  return "default";
}

function severityTone(s: string) {
  if (s === "high") return "destructive";
  if (s === "medium") return "warning";
  return "default";
}

function StagesList({ plan }: { plan: InterviewPlan }) {
  return (
    <ol className="space-y-2">
      {plan.stages.map((s, i) => (
        <li key={`${s.name}-${i}`} className="rounded-md border border-border p-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="font-medium text-sm">{i + 1}. {s.name}</span>
            <span className="text-xs text-muted-foreground">
              ~{s.typical_duration_minutes} min
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1">{s.description}</p>
        </li>
      ))}
    </ol>
  );
}

function TopicChips({ items }: { items: string[] }) {
  if (!items.length) return <EmptyState title="None detected" />;
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((t) => (
        <Badge key={t} variant="secondary">
          {t}
        </Badge>
      ))}
    </div>
  );
}

function RiskAreas({ plan }: { plan: InterviewPlan }) {
  if (!plan.risk_areas.length) return <EmptyState title="No risk areas flagged" />;
  return (
    <ul className="space-y-2">
      {plan.risk_areas.map((r) => (
        <li key={r.topic} className="rounded-md border border-border p-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{r.topic}</span>
            <Badge variant={severityTone(r.severity)}>{r.severity}</Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-1">{r.reason}</p>
        </li>
      ))}
    </ul>
  );
}

function QuestionList({ planId }: { planId: number }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["interview-questions", planId],
    queryFn: () => interviewApi.listQuestions(planId),
  });
  const generate = useMutation({
    mutationFn: () => interviewApi.generateQuestions(planId),
    onSuccess: () => {
      toast({ title: "Questions generated", kind: "success" });
      qc.invalidateQueries({ queryKey: ["interview-questions", planId] });
    },
    onError: (e) =>
      toast({ title: "Failed", description: (e as Error).message, kind: "error" }),
  });

  if (q.isLoading) return <Skeleton className="h-32 w-full" />;
  const items = q.data?.items ?? [];

  if (!items.length) {
    return (
      <div className="space-y-3">
        <EmptyState title="No questions yet" description="Generate a question bank for this plan." />
        <Button onClick={() => generate.mutate()} disabled={generate.isPending}>
          {generate.isPending ? "Generating…" : "Generate Question Bank"}
        </Button>
      </div>
    );
  }

  const grouped = new Map<string, InterviewQuestion[]>();
  for (const item of items) {
    const key = `${item.category}::${item.topic}`;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(item);
  }

  return (
    <div className="space-y-3">
      {[...grouped.entries()].map(([key, qs]) => {
        const [category, topic] = key.split("::");
        return (
          <div key={key} className="rounded-md border border-border p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-sm">{topic}</span>
              <Badge variant="outline">{category.replace(/_/g, " ")}</Badge>
            </div>
            <ul className="space-y-2">
              {qs.map((it) => (
                <li key={it.id}>
                  <div className="flex items-center gap-2">
                    <Badge variant={difficultyTone(it.difficulty)}>
                      {it.difficulty}
                    </Badge>
                    <span className="text-sm">{it.prompt}</span>
                  </div>
                  {it.answer_outline && (
                    <p className="text-xs text-muted-foreground mt-1 pl-1">
                      {it.answer_outline}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

const HORIZONS: { value: 1 | 3 | 7 | 14; label: string }[] = [
  { value: 1, label: "1 day" },
  { value: 3, label: "3 days" },
  { value: 7, label: "7 days" },
  { value: 14, label: "14 days" },
];

function StudyPlanList({ planId }: { planId: number }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["interview-study-plans", planId],
    queryFn: () => interviewApi.listStudyPlans(planId),
  });
  const [active, setActive] = useState<1 | 3 | 7 | 14>(7);
  const generate = useMutation({
    mutationFn: (horizon: 1 | 3 | 7 | 14) =>
      interviewApi.generateStudyPlan(planId, horizon),
    onSuccess: () => {
      toast({ title: "Study plan ready", kind: "success" });
      qc.invalidateQueries({ queryKey: ["interview-study-plans", planId] });
    },
    onError: (e) =>
      toast({ title: "Failed", description: (e as Error).message, kind: "error" }),
  });

  if (q.isLoading) return <Skeleton className="h-32 w-full" />;
  const plans: InterviewStudyPlan[] = q.data?.items ?? [];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        {HORIZONS.map((h) => {
          const exists = plans.some((p) => p.horizon_days === h.value);
          return (
            <Button
              key={h.value}
              size="sm"
              variant={active === h.value ? "default" : "outline"}
              onClick={() => setActive(h.value)}
            >
              {h.label} {exists ? "·" : ""}
            </Button>
          );
        })}
        <Button
          size="sm"
          variant="secondary"
          onClick={() => generate.mutate(active)}
          disabled={generate.isPending}
        >
          {generate.isPending ? "Generating…" : "Generate"}
        </Button>
      </div>
      {(() => {
        const selected = plans.find((p) => p.horizon_days === active);
        if (!selected) {
          return (
            <EmptyState
              title={`No ${active}-day plan yet`}
              description="Pick a horizon and click Generate."
            />
          );
        }
        return (
          <ol className="space-y-2">
            {selected.blocks.map((b, i) => (
              <li key={`${b.day_label}-${i}`} className="rounded-md border border-border p-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="font-medium text-sm">{b.day_label}: {b.focus}</span>
                  <span className="text-xs text-muted-foreground">
                    {b.duration_minutes} min
                  </span>
                </div>
                <ul className="text-xs text-muted-foreground list-disc list-inside mt-1">
                  {b.activities.map((a, j) => (
                    <li key={j}>{a}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        );
      })()}
    </div>
  );
}

export function InterviewPrepPanel({ applicationId }: { applicationId: number }) {
  const qc = useQueryClient();
  const plan = useQuery({
    queryKey: ["interview-plan", applicationId],
    queryFn: () => interviewApi.getLatestPlan(applicationId),
    retry: false,
  });

  const generate = useMutation({
    mutationFn: () => interviewApi.generatePlan(applicationId),
    onSuccess: () => {
      toast({ title: "Interview plan generated", kind: "success" });
      qc.invalidateQueries({ queryKey: ["interview-plan", applicationId] });
      qc.invalidateQueries({ queryKey: ["interview-prep", "dashboard"] });
    },
    onError: (e) =>
      toast({ title: "Failed", description: (e as Error).message, kind: "error" }),
  });

  if (plan.isLoading) return <Skeleton className="h-48 w-full" />;

  if (!plan.data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GraduationCap className="h-5 w-5" /> Interview Prep
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Generate a tailored prep plan for this application — likely stages,
            topics, and risk areas based on the job and your profile.
          </p>
          <Button
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
            data-testid="generate-interview-plan"
          >
            <Sparkles className="h-4 w-4 mr-2" />
            {generate.isPending ? "Generating…" : "Generate Interview Plan"}
          </Button>
        </CardContent>
      </Card>
    );
  }

  const p = plan.data;
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <CardTitle className="flex items-center gap-2">
            <GraduationCap className="h-5 w-5" /> Interview Prep
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={difficultyTone(p.difficulty)}>
              {p.difficulty.replace(/_/g, " ")}
            </Badge>
            <Badge variant="outline">{p.confidence_score}% confidence</Badge>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => generate.mutate()}
              disabled={generate.isPending}
            >
              Regenerate
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="stages">
          <TabsList>
            <TabsTrigger value="stages">Stages</TabsTrigger>
            <TabsTrigger value="topics">Topics</TabsTrigger>
            <TabsTrigger value="risks">Risks</TabsTrigger>
            <TabsTrigger value="questions">Questions</TabsTrigger>
            <TabsTrigger value="study">Study plan</TabsTrigger>
          </TabsList>
          <TabsContent value="stages">
            <StagesList plan={p} />
          </TabsContent>
          <TabsContent value="topics" className="space-y-4">
            <div>
              <div className="text-xs uppercase text-muted-foreground mb-1">Technical</div>
              <TopicChips items={p.technical_topics} />
            </div>
            <div>
              <div className="text-xs uppercase text-muted-foreground mb-1">Behavioral</div>
              <TopicChips items={p.behavioral_topics} />
            </div>
            <div>
              <div className="text-xs uppercase text-muted-foreground mb-1">
                Company prep
              </div>
              <ul className="list-disc list-inside text-sm text-muted-foreground">
                {p.company_prep.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          </TabsContent>
          <TabsContent value="risks">
            <RiskAreas plan={p} />
          </TabsContent>
          <TabsContent value="questions">
            <QuestionList planId={p.id} />
          </TabsContent>
          <TabsContent value="study">
            <StudyPlanList planId={p.id} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
