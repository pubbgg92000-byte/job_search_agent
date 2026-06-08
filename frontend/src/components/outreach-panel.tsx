import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessagesSquare, Sparkles } from "lucide-react";
import {
  outreachApi,
  type DraftMessagePayload,
  type OutreachCampaign,
  type OutreachContact,
  type OutreachMessage,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Textarea } from "@/components/ui/inputs";
import { EmptyState, Skeleton } from "@/components/ui/state";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/lib/toast";

const KINDS: { value: string; label: string }[] = [
  { value: "initial_outreach", label: "Initial outreach" },
  { value: "referral_request", label: "Referral request" },
  { value: "hiring_manager_intro", label: "Hiring manager intro" },
  { value: "follow_up", label: "Follow-up" },
  { value: "thank_you", label: "Thank-you" },
];

function statusTone(s: string) {
  if (s === "interview" || s === "replied") return "success";
  if (s === "ignored") return "destructive";
  if (s === "closed") return "outline";
  if (s === "sent") return "default";
  return "secondary";
}

function MessageList({ messages }: { messages: OutreachMessage[] }) {
  if (!messages.length) return <EmptyState title="No messages drafted yet" />;
  return (
    <ul className="space-y-3">
      {messages.map((m) => (
        <li key={m.id} className="rounded-md border border-border p-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="text-sm font-medium">
              {m.kind.replace(/_/g, " ")}
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline">{m.channel}</Badge>
              {m.sent_at && <Badge variant="success">sent</Badge>}
              {m.replied_at && <Badge variant="success">replied</Badge>}
            </div>
          </div>
          {m.subject && (
            <div className="text-xs text-muted-foreground mt-1">
              Subject: {m.subject}
            </div>
          )}
          <pre className="mt-2 whitespace-pre-wrap font-sans text-sm">{m.body}</pre>
        </li>
      ))}
    </ul>
  );
}

function CampaignBlock({
  applicationId,
  contact,
  campaign,
}: {
  applicationId: number;
  contact: OutreachContact;
  campaign: OutreachCampaign;
}) {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ["outreach-campaign", campaign.id],
    queryFn: () => outreachApi.getCampaign(campaign.id),
  });

  const [kind, setKind] = useState<string>("initial_outreach");
  const [roleTitle, setRoleTitle] = useState<string>("");
  const [extraNotes, setExtraNotes] = useState<string>("");

  const draft = useMutation({
    mutationFn: () => {
      const payload: DraftMessagePayload = {
        kind,
        role_title: roleTitle || undefined,
      };
      return outreachApi.draftMessage(campaign.id, payload);
    },
    onSuccess: () => {
      toast({ title: "Message drafted", kind: "success" });
      qc.invalidateQueries({ queryKey: ["outreach-campaign", campaign.id] });
    },
    onError: (e) =>
      toast({ title: "Failed", description: (e as Error).message, kind: "error" }),
  });

  const markSent = useMutation({
    mutationFn: (messageId: number) => outreachApi.markSent(campaign.id, messageId, 7),
    onSuccess: () => {
      toast({ title: "Marked as sent", kind: "success" });
      qc.invalidateQueries({ queryKey: ["outreach-campaign", campaign.id] });
      qc.invalidateQueries({ queryKey: ["outreach-campaigns", applicationId] });
    },
  });

  const setStatus = useMutation({
    mutationFn: (next: string) => outreachApi.patchCampaignStatus(campaign.id, next),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["outreach-campaign", campaign.id] });
      qc.invalidateQueries({ queryKey: ["outreach-campaigns", applicationId] });
    },
  });

  return (
    <div className="rounded-md border border-border p-3 space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <div className="text-sm font-medium">
            {contact.name} <span className="text-xs text-muted-foreground">({contact.kind.replace(/_/g, " ")})</span>
          </div>
          <div className="text-xs text-muted-foreground">{contact.company}</div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={statusTone(campaign.status)}>{campaign.status}</Badge>
          {(["replied", "interview", "closed"] as const).map((s) => (
            <Button
              key={s}
              size="sm"
              variant="ghost"
              onClick={() => setStatus.mutate(s)}
            >
              {s}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <select
          className="border border-border bg-background rounded-md px-3 text-sm"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
        <Input
          placeholder="Role title (optional)"
          value={roleTitle}
          onChange={(e) => setRoleTitle(e.target.value)}
        />
      </div>
      <Textarea
        placeholder="Notes (not included in message)"
        value={extraNotes}
        onChange={(e) => setExtraNotes(e.target.value)}
        rows={2}
      />
      <div className="flex items-center justify-end gap-2">
        <Button onClick={() => draft.mutate()} disabled={draft.isPending}>
          <Sparkles className="h-4 w-4 mr-2" />
          {draft.isPending ? "Drafting…" : "Draft message"}
        </Button>
      </div>

      {detail.isLoading ? (
        <Skeleton className="h-16 w-full" />
      ) : (
        <>
          <MessageList messages={detail.data?.messages ?? []} />
          {detail.data?.messages?.length ? (
            <div className="flex justify-end">
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  markSent.mutate(detail.data!.messages[detail.data!.messages.length - 1].id)
                }
                disabled={markSent.isPending}
              >
                {markSent.isPending ? "Saving…" : "Mark last message sent"}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function AddContactInline({
  applicationId,
  company,
}: {
  applicationId: number;
  company: string | null;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [kind, setKind] = useState("recruiter");
  const m = useMutation({
    mutationFn: async () => {
      const contact = await outreachApi.upsertContact({
        company: company || "",
        name,
        kind,
      });
      return outreachApi.createCampaign({
        contact_id: contact.id,
        application_id: applicationId,
        goal: "initial_outreach",
      });
    },
    onSuccess: () => {
      toast({ title: "Campaign started", kind: "success" });
      qc.invalidateQueries({ queryKey: ["outreach-campaigns", applicationId] });
      setName("");
    },
    onError: (e) =>
      toast({ title: "Failed", description: (e as Error).message, kind: "error" }),
  });
  if (!company) {
    return (
      <p className="text-xs text-muted-foreground">
        Set the company on this application to start outreach.
      </p>
    );
  }
  return (
    <form
      className="flex items-center gap-2 flex-wrap"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) m.mutate();
      }}
    >
      <Input
        placeholder="Contact name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="flex-1 min-w-[12rem]"
      />
      <select
        className="border border-border bg-background rounded-md px-3 text-sm h-9"
        value={kind}
        onChange={(e) => setKind(e.target.value)}
      >
        <option value="recruiter">Recruiter</option>
        <option value="talent_partner">Talent Partner</option>
        <option value="hiring_manager">Hiring Manager</option>
      </select>
      <Button size="sm" type="submit" disabled={m.isPending || !name.trim()}>
        {m.isPending ? "Adding…" : "Start campaign"}
      </Button>
    </form>
  );
}

export function OutreachPanel({
  applicationId,
  company,
}: {
  applicationId: number;
  company: string | null;
}) {
  const campaigns = useQuery({
    queryKey: ["outreach-campaigns", applicationId],
    queryFn: () =>
      outreachApi.listCampaigns({ /* contact_id omitted */ }).then((r) => ({
        items: r.items.filter((c) => c.application_id === applicationId),
        total: r.items.filter((c) => c.application_id === applicationId).length,
      })),
  });
  const contacts = useQuery({
    queryKey: ["outreach-contacts", company],
    queryFn: () =>
      company
        ? outreachApi.listContacts({ company })
        : Promise.resolve({ items: [] as OutreachContact[], total: 0 }),
  });

  if (campaigns.isLoading || contacts.isLoading)
    return <Skeleton className="h-32 w-full" />;

  const list = campaigns.data?.items ?? [];
  const contactsById = new Map<number, OutreachContact>();
  for (const c of contacts.data?.items ?? []) contactsById.set(c.id, c);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessagesSquare className="h-5 w-5" /> Outreach
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="campaigns">
          <TabsList>
            <TabsTrigger value="campaigns">Campaigns ({list.length})</TabsTrigger>
            <TabsTrigger value="add">New campaign</TabsTrigger>
          </TabsList>
          <TabsContent value="campaigns" className="space-y-3">
            {list.length === 0 ? (
              <EmptyState
                title="No campaigns for this application"
                description="Use the New campaign tab to start one."
              />
            ) : (
              list.map((c) => {
                const contact = contactsById.get(c.contact_id);
                if (!contact) {
                  return (
                    <div
                      key={c.id}
                      className="rounded-md border border-border p-3 text-sm text-muted-foreground"
                    >
                      Campaign #{c.id} — contact details not loaded.
                    </div>
                  );
                }
                return (
                  <CampaignBlock
                    key={c.id}
                    applicationId={applicationId}
                    contact={contact}
                    campaign={c}
                  />
                );
              })
            )}
          </TabsContent>
          <TabsContent value="add">
            <AddContactInline applicationId={applicationId} company={company} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
