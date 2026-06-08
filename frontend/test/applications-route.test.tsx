import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { jsonResponse, mockFetch, renderInRouter } from "./util";
import * as ApplicationsModule from "@/routes/applications.index";

describe("Applications route", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders the applications table from the API", async () => {
    mockFetch(async (url) => {
      if (url.startsWith("/api/applications")) {
        return jsonResponse({
          total: 1,
          limit: 200,
          offset: 0,
          items: [
            {
              id: 1,
              user_id: 1,
              company: "Acme",
              title: "Engineer",
              url: null,
              source: "greenhouse",
              status: "applied",
              created_at: "2026-03-01T00:00:00Z",
              last_updated: "2026-03-02T00:00:00Z",
              discovered_job_id: null,
              artifact_id: null,
              job_id: null,
              recruiter_name: null,
              recruiter_email: null,
              notes: null,
            },
          ],
        });
      }
      return jsonResponse({});
    });
    const Component = (ApplicationsModule as { Route: { options: { component: React.FC } } })
      .Route.options.component;
    renderInRouter(<Component />);
    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());
    expect(screen.getByText("Engineer")).toBeInTheDocument();
    expect(screen.getByTestId("status-badge")).toHaveTextContent("Applied");
  });

  it("shows an empty state when there are no applications", async () => {
    mockFetch(async () =>
      jsonResponse({ total: 0, limit: 200, offset: 0, items: [] }),
    );
    const Component = (ApplicationsModule as { Route: { options: { component: React.FC } } })
      .Route.options.component;
    renderInRouter(<Component />);
    await waitFor(() =>
      expect(screen.getByText(/no applications yet/i)).toBeInTheDocument(),
    );
  });
});
