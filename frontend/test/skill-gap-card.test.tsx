import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SkillGapCard } from "@/components/skill-gap-card";

describe("<SkillGapCard />", () => {
  it("renders skill, frequency, and importance", () => {
    render(
      <SkillGapCard
        gap={{ skill: "rust", frequency: 12, importance_score: 73 }}
      />,
    );
    expect(screen.getByText("rust")).toBeInTheDocument();
    expect(screen.getByText(/12 jobs/i)).toBeInTheDocument();
    expect(screen.getByText(/Importance 73/i)).toBeInTheDocument();
  });

  it("singularises 'job' when frequency is 1", () => {
    render(
      <SkillGapCard
        gap={{ skill: "rust", frequency: 1, importance_score: 10 }}
      />,
    );
    expect(screen.getByText("1 job")).toBeInTheDocument();
  });

  it("clamps importance bar at 100", () => {
    render(
      <SkillGapCard
        gap={{ skill: "foo", frequency: 5, importance_score: 250 }}
      />,
    );
    expect(screen.getByLabelText(/importance 100/i)).toBeInTheDocument();
  });
});
