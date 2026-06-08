import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  outreachApi,
  type OutreachCampaign,
  type OutreachContact,
  type OutreachDashboard,
  type OutreachMetrics,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, PageError, Skeleton } from "@/components/ui/state";
import { Input } from "@/components/ui/inputs";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/outreach/")({
  component: OutreachPage,
});

function statusTone(s: string) {
  if (s === "interview" || s === "replied") return "success";
  if (s === "ignored") return "destructive";
  if (s === "closed") return "outline";
  if (s === "sent") return "default";
  return "secondary";
}

function pct(v: number) {
  return `${Math.round(v * 100)}%`;
}

function MetricsCard({ metrics }: { metrics: OutreachMetrics }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Response Rates</CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-xs text-muted-foreground">Sent</div>
          <div className="text-xl font-semibold">{metrics.sent}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Replies</div>
          <div className="text-xl font-semibold">
            {metrics.replied}{" "}
            <span className="text-xs font-normal text-muted-foreground">
              ({pct(metrics.response_rate)})
            </span>
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Interviews</div>
          <div className="text-xl font-semibold">
            {metrics.interviews}{" "}
            <span className="text-xs font-normal text-muted-foreground">
              ({pct(metrics.interview_rate)})
            </span>
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Referral rate</div>
          <div className="text-xl font-semibold">
            {pct(metrics.referral_rate)}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function CampaignList({
  rows,
  emptyTitle,
}: {
  rows: OutreachCampaign[];
  emptyTitle: string;
}) {
  if (!rows.length) return <EmptyState title={emptyTitle} />;
  return (
    <ul className="space-y-2">
      {rows.map((c) => (
        <li key={c.id} className="rounded-md border border-border p-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div>
              <div className="text-sm font-medium">Campaign #{c.id}</div>
              <div className="text-xs text-muted-foreground">
                goal: {c.goal} · contact {c.contact_id}
              </div>
            </div>
            <Badge variant={statusTone(c.status)}>{c.status}</Badge>
          </div>
          {c.follow_up_due_at && (
            <div className="text-xs text-muted-foreground mt-1">
              follow-up due {new Date(c.follow_up_due_at).toLocaleDateString()}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function ContactsCard({ rows }: { rows: OutreachContact[] }) {
  if (!rows.length) {
    return (
      <EmptyState
        title="No contacts yet"
        description="Add a recruiter or hiring manager below to start outreach."
      />
    );
  }
  return (
    <ul className="space-y-2">
      {rows.map((c) => (
        <li key={c.id} className="rounded-md border border-border p-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div>
              <div className="text-sm font-medium">{c.name}</div>
              <div className="text-xs text-muted-foreground">
                {c.company} · {c.role || c.kind.replace(/_/g, " ")}
              </div>
            </div>
            <Badge variant="outline">{c.confidence}%</Badge>
          </div>
          {c.linkedin_url && (
            <a
              href={c.linkedin_url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary hover:underline break-all"
            >
              {c.linkedin_url}
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}

function AddContactForm() {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    company: "",
    name: "",
    kind: "recruiter",
    role: "",
    linkedin_url: "",
    email: "",
  });
  const m = useMutation({
    mutationFn: () =>
      outreachApi.upsertContact({
        company: form.company,
        name: form.name,
        kind: form.kind,
        role: form.role || undefined,
        linkedin_url: form.linkedin_url || undefined,
        email: form.email || undefined,
      }),
    onSuccess: () => {
      toast({ title: "Contact saved", kind: "success" });
      qc.invalidateQueries({ queryKey: ["outreach", "dashboard"] });
      setForm({ ...form, name: "", role: "", linkedin_url: "", email: "" });
    },
    onError: (e) =>
      toast({ title: "Failed", description: (e as Error).message, kind: "error" }),
  });
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
    >
      <div className="grid grid-cols-2 gap-2">
        <Input
          placeholder="Company"
          value={form.company}
          onChange={(e) => setForm({ ...form, company: e.target.value })}
          required
        />
        <Input
          placeholder="Name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        <Input
          placeholder="Role"
          value={form.role}
          onChange={(e) => setForm({ ...form, role: e.target.value })}
        />
        <select
          className="border border-border bg-background rounded-md px-3 text-sm"
          value={form.kind}
          onChange={(e) => setForm({ ...form, kind: e.target.value })}
        >
          <option value="recruiter">Recruiter</option>
          <option value="talent_partner">Talent Partner</option>
          <option value="hiring_manager">Hiring Manager</option>
          <option value="engineer">Engineer</option>
        </select>
        <Input
          placeholder="LinkedIn URL"
          value={form.linkedin_url}
          onChange={(e) => setForm({ ...form, linkedin_url: e.target.value })}
        />
        <Input
          placeholder="Email"
          type="email"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
      </div>
      <div className="flex justify-end">
        <Button size="sm" type="submit" disabled={m.isPending}>
          {m.isPending ? "Saving…" : "Add contact"}
        </Button>
      </div>
    </form>
  );
}

function OutreachPage() {
  const q = useQuery({
    queryKey: ["outreach", "dashboard"],
    queryFn: () => outreachApi.dashboard(),
  });
  if (q.isLoading) return <Skeleton className="h-64 w-full" />;
  if (q.isError) return <PageError message={(q.error as Error).message} />;
  const data: OutreachDashboard = q.data!;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Outreach</h1>
        <p className="text-sm text-muted-foreground">
          Recruiter and hiring-manager outreach with response-rate tracking.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <MetricsCard metrics={data.metrics} />

        <Card>
          <CardHeader>
            <CardTitle>Follow-ups due</CardTitle>
          </CardHeader>
          <CardContent>
            <CampaignList
              rows={data.due_follow_ups}
              emptyTitle="No follow-ups due — nice work."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent replies</CardTitle>
          </CardHeader>
          <CardContent>
            <CampaignList
              rows={data.recent_replies}
              emptyTitle="No replies yet."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent campaigns</CardTitle>
          </CardHeader>
          <CardContent>
            <CampaignList
              rows={data.recent_campaigns}
              emptyTitle="No campaigns yet."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Contacts</CardTitle>
          </CardHeader>
          <CardContent>
            <ContactsCard rows={data.recent_contacts} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Add contact</CardTitle>
          </CardHeader>
          <CardContent>
            <AddContactForm />
          </CardContent>
        </Card>
      </div>

      <p className="text-xs text-muted-foreground">
        Open an{" "}
        <Link to="/applications" className="text-primary hover:underline">
          application
        </Link>{" "}
        to draft messages tied to a specific role.
      </p>
    </div>
  );
}
