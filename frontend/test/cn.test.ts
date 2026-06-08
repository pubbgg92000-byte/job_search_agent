import { describe, it, expect } from "vitest";
import { cn } from "@/lib/cn";

describe("cn", () => {
  it("merges class strings, dropping falsy and deduping tailwind conflicts", () => {
    expect(cn("p-2", false && "hidden", "p-4")).toBe("p-4");
  });
  it("passes through arrays and objects", () => {
    expect(cn(["a", { b: true, c: false }])).toBe("a b");
  });
});
