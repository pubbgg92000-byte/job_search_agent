import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { jsonResponse, mockFetch, renderInRouter } from "./util";
import * as SkillGapsModule from "@/routes/skill-gaps.index";
import type { SkillPlanResponse } from "@/lib/api";

const plan: SkillPlanResponse = {
  report: {
    jobs_considered: 150,
    top_gaps: [
      { skill: "rust", frequency: 30, importance_score: 90 },
      { skill: "go", frequency: 20, importance_score: 60 },
    ],
  },
  seven_day_plan: {
    horizon_days: 7,
    items: [
      { skill: "rust", goal: "Build a small CLI", resources: ["The Rust Book"] },
    ],
  },
  thirty_day_plan: {
    horizon_days: 30,
    items: [
      { skill: "rust", goal: "Ship a service", resources: ["axum docs"] },
    ],
  },
};

describe("Skill gaps route", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders top gaps and the 7-day plan", async () => {
    mockFetch(async (url) => {
      if (url.startsWith("/api/skills/plan")) return jsonResponse(plan);
      return jsonResponse({});
    });
    const Component = (SkillGapsModule as { Route: { options: { component: React.FC } } }).Route
      .options.component;
    renderInRouter(<Component />);
    await waitFor(() => expect(screen.getAllByText("rust").length).toBeGreaterThan(0));
    expect(screen.getByText("go")).toBeInTheDocument();
    expect(screen.getByText(/build a small cli/i)).toBeInTheDocument();
  });
});
