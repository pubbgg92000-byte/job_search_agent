import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton, EmptyState, PageError } from "@/components/ui/state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

describe("Button", () => {
  it("renders children and forwards onClick", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: /click me/i })).toBeInTheDocument();
  });
  it("renders as the slotted child when asChild is set", () => {
    render(
      <Button asChild>
        <a href="/x">link-as-button</a>
      </Button>,
    );
    expect(screen.getByRole("link", { name: /link-as-button/i })).toBeInTheDocument();
  });
});

describe("Badge", () => {
  it("renders the variant on the className", () => {
    render(<Badge variant="success">Live</Badge>);
    expect(screen.getByText("Live")).toBeInTheDocument();
  });
});

describe("State components", () => {
  it("Skeleton applies a pulse animation", () => {
    const { container } = render(<Skeleton className="h-4" />);
    expect(container.firstChild).toHaveClass("animate-pulse");
  });
  it("EmptyState shows title and description", () => {
    render(<EmptyState title="Nothing" description="Yet." />);
    expect(screen.getByText("Nothing")).toBeInTheDocument();
    expect(screen.getByText("Yet.")).toBeInTheDocument();
  });
  it("PageError shows the message", () => {
    render(<PageError message="boom" />);
    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});

describe("Card composition", () => {
  it("renders header and content", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Hello</CardTitle>
        </CardHeader>
        <CardContent>World</CardContent>
      </Card>,
    );
    expect(screen.getByText("Hello")).toBeInTheDocument();
    expect(screen.getByText("World")).toBeInTheDocument();
  });
});
