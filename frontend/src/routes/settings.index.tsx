import { useEffect, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X, Plus } from "lucide-react";
import { api, type Preferences } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label, Checkbox } from "@/components/ui/inputs";
import { Badge } from "@/components/ui/badge";
import { Skeleton, PageError } from "@/components/ui/state";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/settings/")({
  component: SettingsPage,
});

const EMPTY_PREFS: Preferences = {
  preferred_locations: [],
  remote_only: true,
  salary_min: null,
  salary_max: null,
  salary_currency: "USD",
  preferred_roles: [],
  preferred_skills: [],
  excluded_companies: [],
  excluded_keywords: [],
};

function TagList({
  label,
  values,
  onChange,
  placeholder,
}: {
  label: string;
  values: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");
  function add() {
    const v = draft.trim();
    if (!v || values.includes(v)) return;
    onChange([...values, v]);
    setDraft("");
  }
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <div className="flex gap-2 mt-1">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder={placeholder}
        />
        <Button type="button" variant="outline" onClick={add}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      {values.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {values.map((v) => (
            <Badge key={v} variant="secondary" className="gap-1">
              {v}
              <button
                type="button"
                onClick={() => onChange(values.filter((x) => x !== v))}
                aria-label={`Remove ${v}`}
                className="hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function SettingsPage() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["preferences"],
    queryFn: () => api.get<Preferences>("/preferences"),
  });

  const [form, setForm] = useState<Preferences>(EMPTY_PREFS);

  useEffect(() => {
    if (q.data) setForm(q.data);
  }, [q.data]);

  const save = useMutation({
    mutationFn: (p: Preferences) => api.put<Preferences>("/preferences", p),
    onSuccess: (data) => {
      qc.setQueryData(["preferences"], data);
      toast({ title: "Preferences saved", kind: "success" });
    },
    onError: (e) => toast({ title: "Save failed", description: (e as Error).message, kind: "error" }),
  });

  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError) return <PageError message={(q.error as Error).message} />;

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          The matcher reads these every time it ranks jobs.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(form);
        }}
        className="space-y-6"
      >
        <Card>
          <CardHeader>
            <CardTitle>Location & Remote</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <TagList
              label="Preferred locations"
              values={form.preferred_locations}
              onChange={(v) => setForm((f) => ({ ...f, preferred_locations: v }))}
              placeholder="e.g. Bangalore, Remote-IN"
            />
            <label className="flex items-center gap-2">
              <Checkbox
                checked={form.remote_only}
                onChange={(e) => setForm((f) => ({ ...f, remote_only: e.target.checked }))}
                data-testid="remote-only-checkbox"
              />
              <span className="text-sm">Remote roles only</span>
            </label>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Compensation</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            <div>
              <Label className="text-xs">Min salary</Label>
              <Input
                type="number"
                value={form.salary_min ?? ""}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    salary_min: e.target.value ? Number(e.target.value) : null,
                  }))
                }
              />
            </div>
            <div>
              <Label className="text-xs">Max salary</Label>
              <Input
                type="number"
                value={form.salary_max ?? ""}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    salary_max: e.target.value ? Number(e.target.value) : null,
                  }))
                }
              />
            </div>
            <div>
              <Label className="text-xs">Currency</Label>
              <Input
                value={form.salary_currency ?? ""}
                onChange={(e) =>
                  setForm((f) => ({ ...f, salary_currency: e.target.value || null }))
                }
                placeholder="USD"
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Targeting</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <TagList
              label="Target roles"
              values={form.preferred_roles}
              onChange={(v) => setForm((f) => ({ ...f, preferred_roles: v }))}
              placeholder="e.g. Staff Engineer"
            />
            <TagList
              label="Target skills"
              values={form.preferred_skills}
              onChange={(v) => setForm((f) => ({ ...f, preferred_skills: v }))}
              placeholder="e.g. Rust"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Exclusions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <TagList
              label="Excluded companies"
              values={form.excluded_companies}
              onChange={(v) => setForm((f) => ({ ...f, excluded_companies: v }))}
              placeholder="Company name"
            />
            <TagList
              label="Excluded keywords"
              values={form.excluded_keywords}
              onChange={(v) => setForm((f) => ({ ...f, excluded_keywords: v }))}
              placeholder="Keyword in title/desc"
            />
          </CardContent>
        </Card>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => q.data && setForm(q.data)}>
            Reset
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </div>
  );
}
