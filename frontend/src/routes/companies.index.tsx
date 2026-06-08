import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, ApiError, type CompanySnapshot } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/inputs";
import { Button } from "@/components/ui/button";
import { CompanyCard } from "@/components/company-card";
import { Skeleton, EmptyState, PageError } from "@/components/ui/state";

export const Route = createFileRoute("/companies/")({
  component: CompaniesPage,
});

function CompaniesPage() {
  const [pending, setPending] = useState("");
  const [submitted, setSubmitted] = useState("");

  const q = useQuery({
    queryKey: ["company", submitted],
    queryFn: () => api.get<CompanySnapshot>(`/companies/${encodeURIComponent(submitted)}`),
    enabled: !!submitted,
    retry: false,
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Companies</h1>
        <p className="text-sm text-muted-foreground">
          Look up cached intelligence on a company.
        </p>
      </div>

      <Card>
        <CardContent className="p-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setSubmitted(pending.trim());
            }}
            className="flex gap-2"
          >
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={pending}
                onChange={(e) => setPending(e.target.value)}
                placeholder="Company name (e.g. Stripe)"
                className="pl-8"
                data-testid="companies-search"
              />
            </div>
            <Button type="submit" disabled={!pending.trim()}>
              Look up
            </Button>
          </form>
        </CardContent>
      </Card>

      {!submitted && (
        <EmptyState
          title="Search for a company"
          description="Enter a name to see the latest growth & risk signals."
        />
      )}
      {q.isLoading && <Skeleton className="h-48 w-full" />}
      {q.isError && (
        <PageError
          message={
            q.error instanceof ApiError && q.error.status === 404
              ? `No record for "${submitted}" yet.`
              : (q.error as Error).message
          }
        />
      )}
      {q.data && <CompanyCard company={q.data} />}
    </div>
  );
}
