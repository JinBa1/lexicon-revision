import { describe, expect, test } from "vitest";

import { archiveTokens } from "@/theme/tokens";

describe("archiveTokens", () => {
  test("matches the accepted lighter Lexicon palette", () => {
    expect(archiveTokens.colors.paper).toBe("#F8F5EE");
    expect(archiveTokens.colors["paper-raised"]).toBe("#FEFDFB");
    expect(archiveTokens.colors["paper-sunken"]).toBe("#F1EAD7");
    expect(archiveTokens.colors["paper-lock"]).toBe("#FAF9F3");
    expect(archiveTokens.colors["ink-muted"]).toBe("#8C7C5F");
    expect(archiveTokens.colors.rule).toBe("#E2D9C2");
    expect(archiveTokens.colors["rule-soft"]).toBe("#EDE4D0");
    expect(archiveTokens.colors["claret-soft"]).toBe("#F9F4E8");
    expect(archiveTokens.colors["claret-active"]).toBe("#F2E4DE");
  });
});
