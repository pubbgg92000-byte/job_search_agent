import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import type { Preferences } from "@/lib/api";
import { jsonResponse, mockFetch, renderInRouter } from "./util";
import * as SettingsModule from "@/routes/settings.index";

const prefs: Preferences = {
  preferred_locations: ["Bangalore"],
  remote_only: true,
  salary_min: 100000,
  salary_max: 200000,
  salary_currency: "USD",
  preferred_roles: ["Staff"],
  preferred_skills: ["rust"],
  excluded_companies: ["BadCo"],
  excluded_keywords: ["onsite"],
};

describe("Settings route", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("hydrates the form from /preferences and submits PUT on save", async () => {
    let putBody: unknown = null;
    mockFetch(async (url, init) => {
      if (url === "/api/preferences") {
        if (init?.method === "PUT") {
          putBody = JSON.parse(init.body as string);
          return jsonResponse(putBody);
        }
        return jsonResponse(prefs);
      }
      return jsonResponse({});
    });
    const Component = (SettingsModule as { Route: { options: { component: React.FC } } }).Route
      .options.component;
    renderInRouter(<Component />);
    await waitFor(() =>
      expect((screen.getByDisplayValue("100000") as HTMLInputElement).value).toBe("100000"),
    );
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(putBody).not.toBeNull());
    expect((putBody as Preferences).preferred_locations).toContain("Bangalore");
  });

  it("toggles remote_only", async () => {
    mockFetch(async (url) => {
      if (url === "/api/preferences") return jsonResponse({ ...prefs, remote_only: false });
      return jsonResponse({});
    });
    const Component = (SettingsModule as { Route: { options: { component: React.FC } } }).Route
      .options.component;
    renderInRouter(<Component />);
    const checkbox = await screen.findByTestId("remote-only-checkbox");
    expect((checkbox as HTMLInputElement).checked).toBe(false);
    fireEvent.click(checkbox);
    expect((checkbox as HTMLInputElement).checked).toBe(true);
  });
});
