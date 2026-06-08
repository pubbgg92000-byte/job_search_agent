import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { api, type SkillPlanResponse, type LearningPlan } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SkillGapCard } from "@/components/skill-gap-card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Skeleton, EmptyState, PageError } from "@/components/ui/state";

export const Route = createFileRoute("/skill-gaps/")({
  component: SkillGapsPage,
});

function PlanView({ plan }: { plan: LearningPlan }) {
  if (!plan.items.length) {
    return <EmptyState title="No plan items" />;
  }
  return (
    <ol className="space-y-3">
      {plan.items.map((item, idx) => (
        <li key={`${item.skill}-${idx}`}>
          <Card>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center gap-2">
                <div className="h-6 w-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-semibold">
                  {idx + 1}
                </div>
                <div className="font-medium">{item.skill}</div>
              </div>
              <div className="text-sm text-muted-foreground">{item.goal}</div>
              {item.resources.length > 0 && (
                <ul className="text-xs text-muted-foreground list-disc list-inside">
                  {item.resources.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </li>
      ))}
    </ol>
  );
}

function SkillGapsPage() {
  const q = useQuery({
    queryKey: ["skills", "plan"],
    queryFn: () => api.get<SkillPlanResponse>("/skills/plan"),
    retry: false,
  });

  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError) return <PageError message={(q.error as Error).message} />;
  const r = q.data!;
  const top = r.report.top_gaps;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Skill Gaps</h1>
        <p className="text-sm text-muted-foreground">
          Aggregated across {r.report.jobs_considered.toLocaleString()} considered jobs.
        </p>
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">Top Missing Skills</h2>
        {top.length === 0 ? (
          <EmptyState title="No gaps detected" description="Your resume covers the discovered roles well." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {top.map((g) => (
              <SkillGapCard key={g.skill} gap={g} />
            ))}
          </div>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Learning Plan</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="7d">
            <TabsList>
              <TabsTrigger value="7d">7-Day Plan</TabsTrigger>
              <TabsTrigger value="30d">30-Day Plan</TabsTrigger>
            </TabsList>
            <TabsContent value="7d">
              <PlanView plan={r.seven_day_plan} />
            </TabsContent>
            <TabsContent value="30d">
              <PlanView plan={r.thirty_day_plan} />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
