import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import type { DashboardPayload } from "@/lib/api";
import { jsonResponse, mockFetch, renderInRouter } from "./util";
import * as DashboardModule from "@/routes/index";

const payload: DashboardPayload = {
  jobs_found: 42,
  jobs_found_24h: 3,
  high_matches: 7,
  applications: 5,
  applications_by_status: { applied: 5 },
  interviews: 2,
  offers: 1,
  rejections: 0,
  interview_rate: 0.4,
  offer_rate: 0.2,
  skill_gaps: [{ skill: "rust", frequency: 12, importance_score: 80 }],
  latest_sync: null,
  profile_present: true,
};

describe("Dashboard route", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders stats from /dashboard", async () => {
    mockFetch(async (url) => {
      if (url === "/api/dashboard") return jsonResponse(payload);
      if (url.startsWith("/api/jobs/top-matches")) return jsonResponse([]);
      if (url.startsWith("/api/applications")) {
        return jsonResponse({ total: 0, limit: 5, offset: 0, items: [] });
      }
      return jsonResponse({});
    });
    const Component = (DashboardModule as { Route: { options: { component: React.FC } } }).Route
      .options.component;
    renderInRouter(<Component />);
    await waitFor(() => expect(screen.getByText("42")).toBeInTheDocument());
    expect(screen.getByText("Jobs Found")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("Offers")).toBeInTheDocument();
  });
});
