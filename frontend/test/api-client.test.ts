import { describe, it, expect, beforeEach, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import { jsonResponse, mockFetch } from "./util";

describe("api client", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("GETs JSON and returns parsed body", async () => {
    mockFetch(async (url) => {
      expect(url).toBe("/api/jobs");
      return jsonResponse({ items: [{ id: 1 }], total: 1, limit: 20, offset: 0 });
    });
    const result = await api.get<{ items: { id: number }[] }>("/jobs");
    expect(result.items[0].id).toBe(1);
  });

  it("POSTs JSON with the right headers and body", async () => {
    mockFetch(async (url, init) => {
      expect(url).toBe("/api/applications");
      expect(init?.method).toBe("POST");
      const headers = init?.headers as Record<string, string>;
      expect(headers["content-type"]).toBe("application/json");
      expect(JSON.parse(init?.body as string)).toEqual({ id: 1 });
      return jsonResponse({ ok: true });
    });
    await api.post("/applications", { id: 1 });
  });

  it("PATCHes JSON to the right URL", async () => {
    mockFetch(async (url, init) => {
      expect(url).toBe("/api/applications/3/status");
      expect(init?.method).toBe("PATCH");
      return jsonResponse({ ok: true });
    });
    await api.patch("/applications/3/status", { status: "applied" });
  });

  it("throws ApiError with the server's detail on non-2xx", async () => {
    mockFetch(async () =>
      jsonResponse({ detail: "profile not found" }, 404),
    );
    await expect(api.get("/profile/999")).rejects.toMatchObject({
      message: "profile not found",
      status: 404,
    });
  });

  it("ApiError preserves the status and detail payload", async () => {
    mockFetch(async () => jsonResponse({ detail: "bad" }, 400));
    try {
      await api.get("/whatever");
      throw new Error("expected throw");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).status).toBe(400);
    }
  });
});
