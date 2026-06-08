import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ApplicationTimeline, StatusBadge, statusLabel } from "@/components/application-timeline";
import type { ApplicationEvent } from "@/lib/api";

describe("statusLabel", () => {
  it("maps known statuses to human strings", () => {
    expect(statusLabel("interview_scheduled")).toBe("Interview Scheduled");
    expect(statusLabel("offer")).toBe("Offer");
  });
  it("falls back to the raw key", () => {
    expect(statusLabel("foo")).toBe("foo");
  });
});

describe("<StatusBadge />", () => {
  it("renders the label and the badge", () => {
    render(<StatusBadge status="applied" />);
    expect(screen.getByTestId("status-badge")).toHaveTextContent("Applied");
  });
});

describe("<ApplicationTimeline />", () => {
  it("shows an empty state with no events", () => {
    render(<ApplicationTimeline events={[]} />);
    expect(screen.getByText(/no events recorded/i)).toBeInTheDocument();
  });

  it("orders events chronologically and highlights unusual ones", () => {
    const events: ApplicationEvent[] = [
      {
        id: 1,
        application_id: 1,
        from_status: null,
        to_status: "saved",
        event_type: "status_change",
        occurred_at: "2026-03-01T10:00:00Z",
        notes: null,
      },
      {
        id: 2,
        application_id: 1,
        from_status: "saved",
        to_status: "applied",
        event_type: "status_change",
        occurred_at: "2026-03-02T10:00:00Z",
        notes: "Submitted via portal",
      },
      {
        id: 3,
        application_id: 1,
        from_status: "applied",
        to_status: "saved",
        event_type: "status_change_unusual",
        occurred_at: "2026-03-03T10:00:00Z",
        notes: null,
      },
    ];
    render(<ApplicationTimeline events={events} />);
    expect(screen.getByText(/submitted via portal/i)).toBeInTheDocument();
    expect(screen.getByText("unusual")).toBeInTheDocument();
  });
});
