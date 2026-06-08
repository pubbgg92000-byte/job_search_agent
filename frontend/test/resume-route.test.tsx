import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { jsonResponse, mockFetch, renderInRouter } from "./util";
import * as ResumeModule from "@/routes/resume.index";

describe("Resume route", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders 'profile on file' when dashboard reports profile_present", async () => {
    mockFetch(async (url) => {
      if (url === "/api/dashboard") {
        return jsonResponse({
          jobs_found: 1,
          jobs_found_24h: 0,
          high_matches: 0,
          applications: 0,
          applications_by_status: {},
          interviews: 0,
          offers: 0,
          rejections: 0,
          interview_rate: 0,
          offer_rate: 0,
          skill_gaps: [],
          latest_sync: null,
          profile_present: true,
        });
      }
      return jsonResponse({});
    });
    const Component = (ResumeModule as { Route: { options: { component: React.FC } } }).Route
      .options.component;
    renderInRouter(<Component />);
    await waitFor(() => expect(screen.getByText(/profile on file/i)).toBeInTheDocument());
  });

  it("prompts upload when no profile is present", async () => {
    mockFetch(async () =>
      jsonResponse({
        jobs_found: 0,
        jobs_found_24h: 0,
        high_matches: 0,
        applications: 0,
        applications_by_status: {},
        interviews: 0,
        offers: 0,
        rejections: 0,
        interview_rate: 0,
        offer_rate: 0,
        skill_gaps: [],
        latest_sync: null,
        profile_present: false,
      }),
    );
    const Component = (ResumeModule as { Route: { options: { component: React.FC } } }).Route
      .options.component;
    renderInRouter(<Component />);
    await waitFor(() => expect(screen.getByText(/no resume uploaded yet/i)).toBeInTheDocument());
  });
});
