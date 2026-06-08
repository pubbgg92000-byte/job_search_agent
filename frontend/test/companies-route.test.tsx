import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { jsonResponse, mockFetch, renderInRouter } from "./util";
import * as CompaniesModule from "@/routes/companies.index";

describe("Companies route", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("looks up a company and renders the card", async () => {
    mockFetch(async (url) => {
      if (url.startsWith("/api/companies/")) {
        return jsonResponse({
          name: "Acme",
          website: null,
          industry: "Software",
          company_size: null,
          funding_stage: null,
          remote_policy: null,
          growth_score: 60,
          risk_score: 30,
          summary: null,
          apply_recommendation: true,
          last_updated_at: null,
        });
      }
      return jsonResponse({});
    });
    const Component = (CompaniesModule as { Route: { options: { component: React.FC } } }).Route
      .options.component;
    renderInRouter(<Component />);
    fireEvent.change(await screen.findByTestId("companies-search"), { target: { value: "Acme" } });
    fireEvent.click(screen.getByRole("button", { name: /look up/i }));
    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());
    expect(screen.getByText("Software")).toBeInTheDocument();
  });

  it("renders a 'no record' message on 404", async () => {
    mockFetch(async () => jsonResponse({ detail: "company not found" }, 404));
    const Component = (CompaniesModule as { Route: { options: { component: React.FC } } }).Route
      .options.component;
    renderInRouter(<Component />);
    fireEvent.change(await screen.findByTestId("companies-search"), { target: { value: "Ghost" } });
    fireEvent.click(screen.getByRole("button", { name: /look up/i }));
    await waitFor(() => expect(screen.getByText(/no record for "Ghost"/i)).toBeInTheDocument());
  });
});
