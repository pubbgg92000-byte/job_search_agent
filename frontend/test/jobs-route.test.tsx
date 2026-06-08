import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { jsonResponse, mockFetch, renderInRouter } from "./util";
import * as JobsModule from "@/routes/jobs.index";
import type { JobList } from "@/lib/api";

const jobs: JobList = {
  total: 2,
  limit: 20,
  offset: 0,
  items: [
    {
      id: 1,
      source: "greenhouse",
      source_job_id: "g1",
      company: "Acme",
      title: "Engineer",
      location: "Remote",
      remote: true,
      url: "https://example.com/1",
      posted_at: null,
      salary_min: null,
      salary_max: null,
      salary_currency: null,
    },
    {
      id: 2,
      source: "lever",
      source_job_id: "l2",
      company: "Globex",
      title: "Architect",
      location: "NYC",
      remote: false,
      url: "https://example.com/2",
      posted_at: null,
      salary_min: null,
      salary_max: null,
      salary_currency: null,
    },
  ],
};

describe("Jobs route", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders jobs from the API", async () => {
    mockFetch(async (url) => {
      if (url.startsWith("/api/jobs")) return jsonResponse(jobs);
      return jsonResponse({});
    });
    const Component = (JobsModule as { Route: { options: { component: React.FC } } }).Route.options
      .component;
    renderInRouter(<Component />);
    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());
    expect(screen.getByText("Globex")).toBeInTheDocument();
  });

  it("client-filters by the search box", async () => {
    mockFetch(async () => jsonResponse(jobs));
    const Component = (JobsModule as { Route: { options: { component: React.FC } } }).Route.options
      .component;
    renderInRouter(<Component />);
    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());
    fireEvent.change(screen.getByTestId("jobs-search"), { target: { value: "Globex" } });
    expect(screen.queryByText("Acme")).not.toBeInTheDocument();
    expect(screen.getByText("Globex")).toBeInTheDocument();
  });
});
