import { useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Download } from "lucide-react";
import { api, type DashboardPayload } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton, EmptyState, PageError } from "@/components/ui/state";
import { toast } from "@/lib/toast";

export const Route = createFileRoute("/resume/")({
  component: ResumePage,
});

type UploadResult = {
  profile_id: number;
  name: string | null;
  skills_count: number;
  experience_count: number;
};

function ResumePage() {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [lastUpload, setLastUpload] = useState<UploadResult | null>(null);

  const dash = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardPayload>("/dashboard"),
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api.postForm<UploadResult>("/profile", fd);
    },
    onSuccess: (data) => {
      setLastUpload(data);
      toast({ title: "Resume uploaded", description: `Profile #${data.profile_id}`, kind: "success" });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) => toast({ title: "Upload failed", description: (err as Error).message, kind: "error" }),
  });

  function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) upload.mutate(f);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Resume</h1>
        <p className="text-sm text-muted-foreground">
          Upload your master resume — it's used for tailoring and matching.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Master Resume</CardTitle>
        </CardHeader>
        <CardContent>
          {dash.isLoading && <Skeleton className="h-12 w-full" />}
          {dash.isError && <PageError message={(dash.error as Error).message} />}
          {dash.data && (
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex-1 min-w-0">
                {dash.data.profile_present ? (
                  <div className="text-sm">
                    <span className="font-medium">Profile on file.</span>{" "}
                    <span className="text-muted-foreground">
                      Upload a new PDF to replace.
                    </span>
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">No resume uploaded yet.</div>
                )}
              </div>
              <input
                ref={inputRef}
                type="file"
                accept="application/pdf"
                onChange={onPick}
                className="hidden"
                data-testid="resume-file-input"
              />
              <Button onClick={() => inputRef.current?.click()} disabled={upload.isPending}>
                <FileUp className="h-4 w-4" />
                {upload.isPending ? "Uploading…" : "Upload PDF"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {lastUpload && (
        <Card>
          <CardHeader>
            <CardTitle>Parsed Profile</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-1">
            <div>Name: {lastUpload.name ?? "—"}</div>
            <div>Skills detected: {lastUpload.skills_count}</div>
            <div>Experience entries: {lastUpload.experience_count}</div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Tailored Resumes</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="Generate from a job"
            description='Open any job and click "Generate Tailored Resume" to produce an ATS-scored version and a cover letter. Downloads land as .md.'
          />
          <div className="mt-3 text-xs text-muted-foreground inline-flex items-center gap-1">
            <Download className="h-3 w-3" /> Download lives in the tailor dialog.
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
