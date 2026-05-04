import { describe, expect, test } from "vitest";

import {
  LANDING_HERO_COPY,
  PRODUCT_NAME,
  PROJECT_DISCUSSIONS_URL,
  PROJECT_ISSUES_URL,
  PROJECT_REPOSITORY_URL,
} from "@/lib/publicCopy";

describe("public copy", () => {
  test("centralizes launch-facing brand and support values", () => {
    expect(PRODUCT_NAME).toBe("LEXICON REVISION");
    expect(LANDING_HERO_COPY).toEqual({
      eyebrow: "REVISION WITH SOURCES",
      title: "A better way through past papers",
      lead: "Ask about topics, patterns, or specific questions across past-paper collections. Spend less time scrolling through PDFs, and more time understanding what were examined. ",
    });
    expect(PROJECT_REPOSITORY_URL).toBe("https://github.com/JinBa1/lexicon-revision");
    expect(PROJECT_ISSUES_URL).toBe("https://github.com/JinBa1/lexicon-revision/issues");
    expect(PROJECT_DISCUSSIONS_URL).toBe("https://github.com/JinBa1/lexicon-revision/discussions");
  });
});
