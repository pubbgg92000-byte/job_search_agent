import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Search, RefreshCw, ChevronLeft, ChevronRight } from "lucide-react";
import { api, type Job, type JobList, type TopMatch } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Select, Label, Checkbox } from "@/components/ui/inputs";
import { Button } from "@/components/ui/button";
import { JobCard } from "@/components/job-card";
import { Skeleton, EmptyState, PageError } from "@/components/ui/state";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/jobs/")({
  component: JobsPage,
});

const PAGE_SIZE = 20;

function JobsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [company, setCompany] = useState("");
  const [source, setSource] = useState("");
  const [remoteOnly, setRemoteOnly] = useState(false);
  const [minScore, setMinScore] = useState(0);
  const [sort, setSort] = useState<"posted_at" | "company" | "first_seen_at" | "match_score">(
    "posted_at",
  );
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(0);

  const usingMatchSort = sort === "match_score";

  const listQuery = useQuery({
    queryKey: ["jobs", { company, source, remoteOnly, sort, order, page }],
    queryFn: () => {
      const p = new URLSearchParams();
      p.set("limit", String(PAGE_SIZE));
      p.set("offset", String(page * PAGE_SIZE));
      if (company) p.set("company", company);
      if (source) p.set("source", source);
      if (remoteOnly) p.set("remote", "true");
      if (!usingMatchSort) {
        p.set("sort", sort);
        p.set("order", order);
      }
      return api.get<JobList>(`/jobs?${p.toString()}`);
    },
    enabled: !usingMatchSort,
  });

  const topMatchQuery = useQuery({
    queryKey: ["jobs", "top-matches", { minScore }],
    queryFn: () =>
      api.get<TopMatch[]>(`/jobs/top-matches?limit=100&min_score=${minScore}`),
    enabled: usingMatchSort,
    retry: false,
  });

  const syncMutation = useMutation({
    mutationFn: () => api.post<{ runs: unknown[] }>("/jobs/sync"),
    onSuccess: (data) => {
      toast({ title: "Sync complete", description: `${data.runs.length} source(s) refreshed`, kind: "success" });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) => toast({ title: "Sync failed", description: (err as Error).message, kind: "error" }),
  });

  const createAppMutation = useMutation({
    mutationFn: (job: Job) =>
      api.post("/applications", { discovered_job_id: job.id, status: "saved" }),
    onSuccess: (_data, job) => {
      toast({ title: "Saved", description: `${job.company} – ${job.title}`, kind: "success" });
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) => toast({ title: "Save failed", description: (err as Error).message, kind: "error" }),
  });

  const applyMutation = useMutation({
    mutationFn: (job: Job) =>
      api.post("/applications", { discovered_job_id: job.id, status: "applied" }),
    onSuccess: (_data, job) => {
      toast({ title: "Application created", description: `${job.company} – ${job.title}`, kind: "success" });
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) => toast({ title: "Apply failed", description: (err as Error).message, kind: "error" }),
  });

  // Client-side search filter (the API doesn't have a fuzzy search field for titles/descriptions)
  const visibleJobs: { job: Job; matchScore?: number; missing?: string[] }[] = (() => {
    if (usingMatchSort) {
      const items = topMatchQuery.data ?? [];
      return items
        .filter((tm) =>
          search
            ? `${tm.job.title} ${tm.job.company}`.toLowerCase().includes(search.toLowerCase())
            : true,
        )
        .filter((tm) => (remoteOnly ? tm.job.remote : true))
        .filter((tm) => (company ? tm.job.company.toLowerCase().includes(company.toLowerCase()) : true))
        .filter((tm) => (source ? tm.job.source === source : true))
        .map((tm) => ({ job: tm.job, matchScore: tm.match.score, missing: tm.match.missing_skills }));
    }
    const items = listQuery.data?.items ?? [];
    const filtered = search
      ? items.filter((j) =>
          `${j.title} ${j.company}`.toLowerCase().includes(search.toLowerCase()),
        )
      : items;
    return filtered.map((j) => ({ job: j }));
  })();

  const total = usingMatchSort ? visibleJobs.length : listQuery.data?.total ?? 0;
  const pages = usingMatchSort ? 1 : Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Jobs</h1>
          <p className="text-sm text-muted-foreground">
            {total.toLocaleString()} discovered postings
          </p>
        </div>
        <Button onClick={() => syncMutation.mutate()} disabled={syncMutation.isPending}>
          <RefreshCw className={syncMutation.isPending ? "animate-spin h-4 w-4" : "h-4 w-4"} />
          Sync
        </Button>
      </div>

      <Card>
        <CardContent className="p-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <div className="lg:col-span-2 relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              data-testid="jobs-search"
              className="pl-8"
              placeholder="Search title or company"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-xs">Company</Label>
            <Input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="any" />
          </div>
          <div>
            <Label className="text-xs">Source</Label>
            <Select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">All</option>
              <option value="greenhouse">Greenhouse</option>
              <option value="lever">Lever</option>
              <option value="ashby">Ashby</option>
              <option value="remoteok">RemoteOK</option>
              <option value="remotive">Remotive</option>
              <option value="wwr">WeWorkRemotely</option>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Sort</Label>
            <Select value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
              <option value="posted_at">Posted</option>
              <option value="first_seen_at">First Seen</option>
              <option value="company">Company</option>
              <option value="match_score">Match Score</option>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Order</Label>
            <Select
              value={order}
              onChange={(e) => setOrder(e.target.value as "asc" | "desc")}
              disabled={usingMatchSort}
            >
              <option value="desc">Desc</option>
              <option value="asc">Asc</option>
            </Select>
          </div>
          <label className="flex items-center gap-2 mt-2 lg:mt-6">
            <Checkbox checked={remoteOnly} onChange={(e) => setRemoteOnly(e.target.checked)} />
            <span className="text-sm">Remote only</span>
          </label>
          {usingMatchSort && (
            <div className="lg:col-span-2">
              <Label className="text-xs">Min Match Score: {minScore}</Label>
              <input
                type="range"
                min={0}
                max={100}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full accent-primary"
              />
            </div>
          )}
        </CardContent>
      </Card>

      {(listQuery.isLoading || topMatchQuery.isLoading) && (
        <div className="grid gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      )}
      {topMatchQuery.isError && usingMatchSort && (
        <PageError message="Match scoring requires a profile. Upload one in Resume." />
      )}
      {listQuery.isError && <PageError message={(listQuery.error as Error).message} />}
      {!listQuery.isLoading && !topMatchQuery.isLoading && visibleJobs.length === 0 && (
        <EmptyState
          title="No jobs found"
          description="Try clearing filters or running a sync."
        />
      )}

      <div className="grid gap-3">
        {visibleJobs.map(({ job, matchScore, missing }) => (
          <JobCard
            key={job.id}
            job={job}
            matchScore={matchScore}
            missingSkills={missing}
            onSave={(j) => createAppMutation.mutate(j)}
            onApply={(j) => applyMutation.mutate(j)}
          />
        ))}
      </div>

      {!usingMatchSort && pages > 1 && (
        <div className="flex items-center justify-between gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            <ChevronLeft className="h-4 w-4" /> Prev
          </Button>
          <div className="text-xs text-muted-foreground">
            Page {page + 1} of {pages}
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pages - 1}
            onClick={() => setPage((p) => p + 1)}
          >
            Next <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
