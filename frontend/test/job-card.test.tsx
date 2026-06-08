import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import type { Job } from "@/lib/api";
import { JobCard, formatSalary } from "@/components/job-card";
import { renderInRouter } from "./util";

const baseJob: Job = {
  id: 7,
  source: "greenhouse",
  source_job_id: "abc",
  company: "Acme",
  title: "Senior Engineer",
  location: "Remote",
  remote: true,
  url: "https://example.com/job",
  posted_at: null,
  salary_min: 150000,
  salary_max: 200000,
  salary_currency: "USD",
};

describe("formatSalary", () => {
  it("renders a range when both bounds present", () => {
    expect(formatSalary(baseJob)).toBe("USD 150k–200k");
  });
  it("returns null when no salary info present", () => {
    expect(
      formatSalary({ salary_min: null, salary_max: null, salary_currency: null }),
    ).toBeNull();
  });
  it("handles single-sided salary", () => {
    expect(
      formatSalary({ salary_min: 120000, salary_max: null, salary_currency: "USD" }),
    ).toBe("USD 120k");
  });
});

describe("<JobCard />", () => {
  it("renders company, title, and match badge", async () => {
    renderInRouter(<JobCard job={baseJob} matchScore={88} />);
    await waitFor(() => expect(screen.getByText("Acme")).toBeInTheDocument());
    expect(screen.getByText("Senior Engineer")).toBeInTheDocument();
    expect(screen.getByTestId("match-score-badge")).toHaveTextContent("88");
  });

  it("calls onSave / onApply when buttons clicked", async () => {
    const onSave = vi.fn();
    const onApply = vi.fn();
    renderInRouter(<JobCard job={baseJob} onSave={onSave} onApply={onApply} />);
    const saveBtn = await screen.findByRole("button", { name: /save/i });
    fireEvent.click(saveBtn);
    fireEvent.click(screen.getByRole("button", { name: /apply/i }));
    expect(onSave).toHaveBeenCalledWith(baseJob);
    expect(onApply).toHaveBeenCalledWith(baseJob);
  });

  it("truncates missing-skills list past 6 entries", async () => {
    const skills = ["a", "b", "c", "d", "e", "f", "g", "h"];
    renderInRouter(<JobCard job={baseJob} missingSkills={skills} />);
    await waitFor(() => expect(screen.getByText(/^\+2$/)).toBeInTheDocument());
  });
});
