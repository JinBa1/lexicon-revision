import { describe, expect, test } from "vitest";

import { PRODUCT_NAME, SUPPORT_EMAIL } from "@/lib/publicCopy";

describe("public copy", () => {
  test("centralizes launch-facing brand and support values", () => {
    expect(PRODUCT_NAME).toBe("LEXICON REVISION");
    expect(SUPPORT_EMAIL).toBe("support@lexicon-revision.example");
  });
});
