import { describe, it, expect, beforeEach } from "vitest";
import { useToastStore, toast } from "@/lib/toast";

describe("toast store", () => {
  beforeEach(() => useToastStore.setState({ toasts: [] }));

  it("appends a toast and assigns an id", () => {
    const id = toast({ title: "Hello", kind: "success" });
    const state = useToastStore.getState();
    expect(state.toasts).toHaveLength(1);
    expect(state.toasts[0].id).toBe(id);
    expect(state.toasts[0].title).toBe("Hello");
  });

  it("dismiss removes a specific toast by id", () => {
    const a = toast({ title: "A" });
    toast({ title: "B" });
    useToastStore.getState().dismiss(a);
    const titles = useToastStore.getState().toasts.map((t) => t.title);
    expect(titles).toEqual(["B"]);
  });

  it("defaults kind to default when omitted", () => {
    toast({ title: "X" });
    expect(useToastStore.getState().toasts[0].kind).toBe("default");
  });
});
