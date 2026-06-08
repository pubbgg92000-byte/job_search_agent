import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { jsonResponse, mockFetch, renderWithProviders } from "./util";
import { ApplyAssistPanel } from "@/components/apply-assist-panel";
import { detectAtsPlatform, type ApplyAssistEnvelope } from "@/lib/api";

function envelope(
  state: ApplyAssistEnvelope["session"]["state"],
  overrides: Partial<ApplyAssistEnvelope["session"]> = {},
): ApplyAssistEnvelope {
  return {
    session: {
      id: 1,
      application_id: 42,
      platform: "greenhouse",
      state,
      headless: true,
      job_url: "https://boards.greenhouse.io/x/jobs/1",
      screenshot_paths: ["/tmp/0.png", "/tmp/1.png"],
      screenshot_count: 2,
      error_message: null,
      started_at: "2026-06-08T00:00:00Z",
      ready_for_review_at: null,
      completed_at: null,
      filled_fields: ["first_name", "email"],
      skipped_fields: ["phone"],
      ...overrides,
    },
    events: [
      { id: 1, event_type: "apply_assist.form_started", notes: null, occurred_at: "2026-06-08T00:00:01Z" },
    ],
  };
}

describe("ApplyAssistPanel", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("calls /start once on mount when no sessionId", async () => {
    const calls: string[] = [];
    mockFetch(async (url, init) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/apply-assist/start")) {
        return jsonResponse(envelope("in_progress"));
      }
      return jsonResponse(envelope("in_progress"));
    });
    renderWithProviders(
      <ApplyAssistPanel
        applicationId={42}
        sessionId={null}
        onSessionCreated={() => {}}
        onDismiss={() => {}}
      />,
    );
    await waitFor(() => {
      expect(calls.some((c) => c === "POST /api/applications/42/apply-assist/start")).toBe(true);
    });
  });

  it("shows the loading state while in_progress", async () => {
    mockFetch(async (url) => {
      if (url.endsWith("/apply-assist/start")) return jsonResponse(envelope("in_progress"));
      return jsonResponse(envelope("in_progress"));
    });
    renderWithProviders(
      <ApplyAssistPanel
        applicationId={42}
        sessionId={1}
        onSessionCreated={() => {}}
        onDismiss={() => {}}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("apply-state")).toHaveTextContent(/filling form/i),
    );
  });

  it("renders screenshots and Approve button when ready_for_review", async () => {
    mockFetch(async () => jsonResponse(envelope("ready_for_review")));
    renderWithProviders(
      <ApplyAssistPanel
        applicationId={42}
        sessionId={1}
        onSessionCreated={() => {}}
        onDismiss={() => {}}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("apply-approve")).toBeInTheDocument());
    const shots = screen.getByTestId("apply-shots");
    expect(shots.querySelectorAll("img").length).toBe(2);
  });

  it("posts to /approve when the Approve button is clicked", async () => {
    const seen: string[] = [];
    mockFetch(async (url, init) => {
      seen.push(`${init?.method ?? "GET"} ${url}`);
      if (url.includes("/approve")) {
        return jsonResponse({ ...envelope("submitted"), application_status: "applied" });
      }
      return jsonResponse(envelope("ready_for_review"));
    });
    renderWithProviders(
      <ApplyAssistPanel
        applicationId={42}
        sessionId={1}
        onSessionCreated={() => {}}
        onDismiss={() => {}}
      />,
    );
    await waitFor(() => screen.getByTestId("apply-approve"));
    fireEvent.click(screen.getByTestId("apply-approve"));
    await waitFor(() =>
      expect(
        seen.some((c) => c === "POST /api/applications/42/apply-assist/sessions/1/approve"),
      ).toBe(true),
    );
  });

  it("shows submitted success when the state is submitted", async () => {
    mockFetch(async () => jsonResponse(envelope("submitted")));
    renderWithProviders(
      <ApplyAssistPanel
        applicationId={42}
        sessionId={1}
        onSessionCreated={() => {}}
        onDismiss={() => {}}
      />,
    );
    await waitFor(() =>
      expect(screen.getByText(/status advanced to/i)).toBeInTheDocument(),
    );
  });

  it("shows error_message when the state is failed", async () => {
    mockFetch(async () =>
      jsonResponse(envelope("failed", { error_message: "form selector missing" })),
    );
    renderWithProviders(
      <ApplyAssistPanel
        applicationId={42}
        sessionId={1}
        onSessionCreated={() => {}}
        onDismiss={() => {}}
      />,
    );
    await waitFor(() =>
      expect(screen.getByText(/form selector missing/i)).toBeInTheDocument(),
    );
  });

  it("posts to /cancel when Cancel is clicked", async () => {
    const seen: string[] = [];
    mockFetch(async (url, init) => {
      seen.push(`${init?.method ?? "GET"} ${url}`);
      if (url.includes("/cancel")) return jsonResponse(envelope("cancelled"));
      return jsonResponse(envelope("ready_for_review"));
    });
    renderWithProviders(
      <ApplyAssistPanel
        applicationId={42}
        sessionId={1}
        onSessionCreated={() => {}}
        onDismiss={() => {}}
      />,
    );
    await waitFor(() => screen.getByTestId("apply-cancel"));
    fireEvent.click(screen.getByTestId("apply-cancel"));
    await waitFor(() =>
      expect(seen.some((c) => c === "POST /api/applications/42/apply-assist/sessions/1/cancel")).toBe(
        true,
      ),
    );
  });

  it("renders error UI when /start fails", async () => {
    mockFetch(async () => jsonResponse({ detail: "no profile uploaded yet" }, 400));
    renderWithProviders(
      <ApplyAssistPanel
        applicationId={42}
        sessionId={null}
        onSessionCreated={() => {}}
        onDismiss={() => {}}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("apply-assist-error")).toBeInTheDocument(),
    );
    expect(screen.getByText(/no profile/i)).toBeInTheDocument();
  });
});

describe("detectAtsPlatform (URL-only)", () => {
  it("recognises greenhouse, lever, ashby host patterns", () => {
    expect(detectAtsPlatform("https://boards.greenhouse.io/stripe/jobs/1")).toBe("greenhouse");
    expect(detectAtsPlatform("https://jobs.lever.co/netflix/abc")).toBe("lever");
    expect(detectAtsPlatform("https://jobs.ashbyhq.com/ramp/x")).toBe("ashby");
  });

  it("recognises greenhouse via gh_jid hint", () => {
    expect(detectAtsPlatform("https://careers.acme.com/jobs/?gh_jid=987")).toBe("greenhouse");
  });

  it("returns unknown for unrelated hosts", () => {
    expect(detectAtsPlatform("https://example.com/jobs/1")).toBe("unknown");
  });

  it("returns unknown for null/empty/garbage", () => {
    expect(detectAtsPlatform(null)).toBe("unknown");
    expect(detectAtsPlatform(undefined)).toBe("unknown");
    expect(detectAtsPlatform("")).toBe("unknown");
    expect(detectAtsPlatform("not-a-url")).toBe("unknown");
  });
});
