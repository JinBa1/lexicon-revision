import { describe, expect, test, vi } from "vitest";

import { shouldRetryQuery } from "@/App";
import { ApiError } from "@/lib/api/errors";

const { mockedEnv } = vi.hoisted(() => ({
  mockedEnv: {
    apiBaseUrl: "http://api.test",
    authMode: "stub_header" as const,
    stubAuthEmail: null,
    clerkPublishableKey: "pk_test_fixture",
    buildSha: "abcdef1234567890",
  },
}));

vi.mock("@/env", () => ({
  env: mockedEnv,
}));

describe("shouldRetryQuery", () => {
  test("does not retry rate-limited API errors", () => {
    const error = new ApiError({
      status: 429,
      code: "rate_limited",
      detail: {
        code: "rate_limited",
        message: "Too many requests. Try again later.",
      },
    });

    expect(shouldRetryQuery(0, error)).toBe(false);
  });

  test("keeps one retry for transport and unexpected errors", () => {
    expect(shouldRetryQuery(0, new Error("network down"))).toBe(true);
    expect(shouldRetryQuery(1, new Error("network down"))).toBe(false);
  });
});
