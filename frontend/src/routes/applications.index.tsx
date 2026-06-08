import { useState, useMemo } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Application, type ApplicationList } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Select, Input, Label } from "@/components/ui/inputs";
import { StatusBadge, statusLabel } from "@/components/application-timeline";
import { Skeleton, EmptyState, PageError } from "@/components/ui/state";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { ChevronDown } from "lucide-react";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/applications/")({
  component: ApplicationsPage,
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

function ApplicationsPage() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");

  const q = useQuery({
    queryKey: ["applications", { statusFilter }],
    queryFn: () => {
      const p = new URLSearchParams({ limit: "200", offset: "0" });
      if (statusFilter) p.set("status", statusFilter);
      return api.get<ApplicationList>(`/applications?${p.toString()}`);
    },
  });

  const items = useMemo(() => {
    const list = q.data?.items ?? [];
    if (!search) return list;
    return list.filter((a) =>
      `${a.company ?? ""} ${a.title ?? ""}`.toLowerCase().includes(search.toLowerCase()),
    );
  }, [q.data, search]);

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.patch(`/applications/${id}/status`, { status }),
    onMutate: async ({ id, status }) => {
      const key = ["applications", { statusFilter }];
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<ApplicationList>(key);
      if (prev) {
        qc.setQueryData<ApplicationList>(key, {
          ...prev,
          items: prev.items.map((a) => (a.id === id ? { ...a, status } : a)),
        });
      }
      return { prev };
    },
    onError: (err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(["applications", { statusFilter }], ctx.prev);
      toast({ title: "Update failed", description: (err as Error).message, kind: "error" });
    },
    onSuccess: () => {
      toast({ title: "Status updated", kind: "success" });
      qc.invalidateQueries({ queryKey: ["applications"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Applications</h1>
        <p className="text-sm text-muted-foreground">
          {(q.data?.total ?? 0).toLocaleString()} tracked applications
        </p>
      </div>

      <Card>
        <CardContent className="p-4 grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <Label className="text-xs">Search</Label>
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Company or role"
              data-testid="apps-search"
            />
          </div>
          <div>
            <Label className="text-xs">Status</Label>
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {statusLabel(s)}
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      {q.isLoading && <Skeleton className="h-64 w-full" />}
      {q.isError && <PageError message={(q.error as Error).message} />}
      {q.data && items.length === 0 && (
        <EmptyState title="No applications yet" description="Save a job from the Jobs page to begin tracking." />
      )}

      {items.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table data-testid="apps-table">
              <THead>
                <TR>
                  <TH>Status</TH>
                  <TH>Company</TH>
                  <TH>Role</TH>
                  <TH className="hidden md:table-cell">Created</TH>
                  <TH className="hidden md:table-cell">Last Updated</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {items.map((a: Application) => (
                  <TR key={a.id}>
                    <TD>
                      <StatusBadge status={a.status} />
                    </TD>
                    <TD className="font-medium">{a.company || "—"}</TD>
                    <TD>
                      <Link
                        to="/applications/$applicationId"
                        params={{ applicationId: String(a.id) }}
                        className="hover:text-primary"
                      >
                        {a.title || "Untitled"}
                      </Link>
                    </TD>
                    <TD className="hidden md:table-cell text-xs text-muted-foreground">
                      {new Date(a.created_at).toLocaleDateString()}
                    </TD>
                    <TD className="hidden md:table-cell text-xs text-muted-foreground">
                      {new Date(a.last_updated).toLocaleDateString()}
                    </TD>
                    <TD className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm">
                            Update <ChevronDown className="h-3 w-3" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          {STATUSES.map((s) => (
                            <DropdownMenuItem
                              key={s}
                              onSelect={() => updateStatus.mutate({ id: a.id, status: s })}
                            >
                              {statusLabel(s)}
                            </DropdownMenuItem>
                          ))}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
