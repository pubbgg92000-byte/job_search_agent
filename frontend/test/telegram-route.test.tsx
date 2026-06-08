import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { jsonResponse, mockFetch, renderInRouter } from "./util";
import * as TelegramModule from "@/routes/telegram.index";

describe("Telegram route", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows configured badge when both token + chat_id are present", async () => {
    mockFetch(async (url) => {
      if (url === "/api/telegram/status") {
        return jsonResponse({
          configured: true,
          chat_id: "12345",
          bot_token_present: true,
          last_digest: {
            generated_at: "2026-06-08T00:00:00Z",
            top_matches: 3,
            jobs_discovered_24h: 7,
            applications_total: 5,
          },
          next_scheduled_at: "2026-06-09T08:00:00Z",
          scheduled_run_at_local: "08:00:00",
        });
      }
      return jsonResponse({});
    });
    const Component = (TelegramModule as { Route: { options: { component: React.FC } } }).Route
      .options.component;
    renderInRouter(<Component />);
    await waitFor(() => expect(screen.getByText(/configured/i)).toBeInTheDocument());
    expect(screen.getByText("12345")).toBeInTheDocument();
  });

  it("warns when telegram is not configured", async () => {
    mockFetch(async () =>
      jsonResponse({
        configured: false,
        chat_id: null,
        bot_token_present: false,
        last_digest: {
          generated_at: null,
          top_matches: 0,
          jobs_discovered_24h: 0,
          applications_total: 0,
        },
        next_scheduled_at: "2026-06-09T08:00:00Z",
        scheduled_run_at_local: "08:00:00",
      }),
    );
    const Component = (TelegramModule as { Route: { options: { component: React.FC } } }).Route
      .options.component;
    renderInRouter(<Component />);
    await waitFor(() => expect(screen.getByText(/missing config/i)).toBeInTheDocument());
  });
});
