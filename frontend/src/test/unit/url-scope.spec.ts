import { describe, expect, test } from "vitest";

import {
  buildAnswerHref,
  buildCollectionHref,
  buildQuestionsHref,
  buildSourceHref,
  buildUnlockHref,
  parseQueryFromSearchParams,
} from "@/lib/url/scope";
import { truncateExcerpt } from "@/lib/url/query";

describe("url scope helpers", () => {
  test("buildCollectionHref escapes path segment", () => {
    expect(buildCollectionHref("cam-cs-tripos")).toBe("/c/cam-cs-tripos");
    expect(buildCollectionHref("with space")).toBe("/c/with%20space");
  });

  test("buildQuestionsHref assembles q and filter params", () => {
    expect(
      buildQuestionsHref({
        collection: "cam-cs-tripos",
        query: "amortized analysis",
        filters: [{ field: "year", op: "eq", value: 2022 }],
      }),
    ).toBe("/c/cam-cs-tripos/questions?q=amortized+analysis&filter=year%3Aeq%3A2022");
  });

  test("buildQuestionsHref keeps q first and preserves filter order", () => {
    expect(
      buildQuestionsHref({
        collection: "cam-cs-tripos",
        query: "range query",
        filters: [
          { field: "year", op: "gte", value: 2018 },
          { field: "year", op: "lte", value: 2025 },
        ],
      }),
    ).toBe(
      "/c/cam-cs-tripos/questions?q=range+query&filter=year%3Agte%3A2018&filter=year%3Alte%3A2025",
    );
  });

  test("buildAnswerHref assembles q and filter params", () => {
    expect(
      buildAnswerHref({
        collection: "cam-cs-tripos",
        query: "how do past papers\u2026",
        filters: [],
      }),
    ).toBe("/c/cam-cs-tripos/answer?q=how+do+past+papers%E2%80%A6");
  });

  test("buildSourceHref includes chunk_id", () => {
    expect(buildSourceHref("cam", "q-1")).toBe("/c/cam/source/q-1");
  });

  test("buildUnlockHref supports optional returnTo", () => {
    expect(buildUnlockHref("cam")).toBe("/unlock/cam");
    expect(buildUnlockHref("cam", "/c/cam/questions?q=algo")).toBe(
      "/unlock/cam?returnTo=%2Fc%2Fcam%2Fquestions%3Fq%3Dalgo",
    );
  });

  test("parseQueryFromSearchParams returns empty string when missing", () => {
    expect(parseQueryFromSearchParams(new URLSearchParams())).toBe("");
  });

  test("parseQueryFromSearchParams returns actual query when present", () => {
    const params = new URLSearchParams();
    params.set("q", "hello world");

    expect(parseQueryFromSearchParams(params)).toBe("hello world");
  });

  test("truncateExcerpt leaves short text unchanged", () => {
    expect(truncateExcerpt("short text", 20)).toBe("short text");
  });

  test("truncateExcerpt truncates with ellipsis", () => {
    expect(truncateExcerpt("abcdefghijklmnop", 8)).toBe("abcdefg…");
  });

  test("truncateExcerpt trims trailing space before ellipsis", () => {
    expect(truncateExcerpt("abcdef ghij", 8)).toBe("abcdef…");
  });
});
