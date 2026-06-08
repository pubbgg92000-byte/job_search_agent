import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CompanyCard, applyLabel } from "@/components/company-card";

describe("applyLabel", () => {
  it("returns null when recommendation is unknown", () => {
    expect(applyLabel(null)).toBeNull();
    expect(applyLabel(undefined)).toBeNull();
  });
  it("maps boolean to label + variant", () => {
    expect(applyLabel(true)).toEqual({ label: "Apply", variant: "success" });
    expect(applyLabel(false)).toEqual({ label: "Avoid", variant: "destructive" });
  });
});

describe("<CompanyCard />", () => {
  it("renders all signals when present", () => {
    render(
      <CompanyCard
        company={{
          name: "Acme",
          website: "https://acme.test",
          industry: "Software",
          company_size: "201-500",
          funding_stage: "Series B",
          remote_policy: "Remote-first",
          growth_score: 72,
          risk_score: 28,
          summary: "Steady scale-up.",
          apply_recommendation: true,
          last_updated_at: null,
        }}
      />,
    );
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("Software")).toBeInTheDocument();
    expect(screen.getByText("Apply")).toBeInTheDocument();
    expect(screen.getByText("Size: 201-500")).toBeInTheDocument();
    expect(screen.getByText("Series B")).toBeInTheDocument();
    expect(screen.getByText("Remote-first")).toBeInTheDocument();
    expect(screen.getByText(/Steady scale-up/i)).toBeInTheDocument();
  });

  it("marks unknown scores rather than guessing", () => {
    render(
      <CompanyCard
        company={{
          name: "Stealth",
          website: null,
          industry: null,
          company_size: null,
          funding_stage: null,
          remote_policy: null,
          growth_score: null,
          risk_score: null,
          summary: null,
          apply_recommendation: null,
          last_updated_at: null,
        }}
      />,
    );
    // four "unknown" badges now — growth, risk, hiring, confidence
    expect(screen.getAllByText(/unknown/i).length).toBeGreaterThanOrEqual(4);
  });

  it("renders Phase 3B fields when present", () => {
    render(
      <CompanyCard
        company={{
          name: "Acme",
          website: null,
          industry: "Fintech",
          company_size: null,
          funding_stage: null,
          remote_policy: null,
          growth_score: 70,
          risk_score: 30,
          summary: null,
          apply_recommendation: true,
          last_updated_at: null,
          confidence_score: 65,
          hiring_velocity_score: 80,
          open_roles_count: 25,
          tech_stack: ["python", "rust", "kafka"],
          layoffs_detected: false,
          news_items: [
            {
              title: "Acme raises $50M",
              summary: "Series B round",
              url: "https://news.test/1",
              published_at: "2026-06-01T00:00:00Z",
              category: "funding",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("python")).toBeInTheDocument();
    expect(screen.getByText("rust")).toBeInTheDocument();
    expect(screen.getByText(/25 open roles/i)).toBeInTheDocument();
    expect(screen.getByText(/Acme raises/i)).toBeInTheDocument();
  });

  it("shows a layoffs badge when detected", () => {
    render(
      <CompanyCard
        company={{
          name: "RiskyCo",
          website: null,
          industry: null,
          company_size: null,
          funding_stage: null,
          remote_policy: null,
          growth_score: 40,
          risk_score: 70,
          summary: null,
          apply_recommendation: false,
          last_updated_at: null,
          layoffs_detected: true,
        }}
      />,
    );
    expect(screen.getByText(/layoffs/i)).toBeInTheDocument();
    expect(screen.getByText("Avoid")).toBeInTheDocument();
  });

  it("renders engineering team signal chips", () => {
    render(
      <CompanyCard
        company={{
          name: "EngCo",
          website: null,
          industry: null,
          company_size: null,
          funding_stage: null,
          remote_policy: null,
          growth_score: null,
          risk_score: null,
          summary: null,
          apply_recommendation: null,
          last_updated_at: null,
          engineering_team_signals: {
            has_engineering_blog: true,
            mentions_open_source: true,
          },
        }}
      />,
    );
    expect(screen.getByText(/has engineering blog/i)).toBeInTheDocument();
    expect(screen.getByText(/mentions open source/i)).toBeInTheDocument();
  });
});
