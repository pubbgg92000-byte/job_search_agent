import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MatchScoreBadge, scoreBucket } from "@/components/match-score-badge";

describe("scoreBucket", () => {
  it("groups scores into high/mid/low buckets", () => {
    expect(scoreBucket(95)).toBe("high");
    expect(scoreBucket(75)).toBe("high");
    expect(scoreBucket(74)).toBe("mid");
    expect(scoreBucket(50)).toBe("mid");
    expect(scoreBucket(49)).toBe("low");
    expect(scoreBucket(0)).toBe("low");
  });
});

describe("<MatchScoreBadge />", () => {
  it("renders the score value", () => {
    render(<MatchScoreBadge score={82} />);
    expect(screen.getByTestId("match-score-badge")).toHaveTextContent("82");
  });

  it("exposes its bucket via data attribute", () => {
    render(<MatchScoreBadge score={40} />);
    expect(screen.getByTestId("match-score-badge")).toHaveAttribute("data-bucket", "low");
  });
});
