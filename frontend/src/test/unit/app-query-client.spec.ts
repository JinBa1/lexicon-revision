import { describe, expect, test, vi } from "vitest";

import { shouldAutoRefetchQuery, shouldRetryQuery } from "@/App";
import { ApiError, isRateLimitBackoffError } from "@/lib/api/errors";

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

function queryWithError(error: unknown) {
  return { state: { error } };
}

describe("shouldRetryQuery", () => {
  test("does not retry or auto-refetch 429 API errors", () => {
    const error = new ApiError({
      status: 429,
      code: "rate_limited",
      detail: {
        code: "rate_limited",
        message: "Too many requests. Try again later.",
      },
    });

    expect(isRateLimitBackoffError(error)).toBe(true);
    expect(shouldRetryQuery(0, error)).toBe(false);
    expect(shouldAutoRefetchQuery(queryWithError(error))).toBe(false);
  });

  test("does not retry or auto-refetch rate-limit-unavailable 503 API errors", () => {
    const error = new ApiError({
      status: 503,
      code: "service_unavailable",
      detail: {
        code: "rate_limit_unavailable",
        message: "Rate-limit backend unavailable.",
      },
    });

    expect(isRateLimitBackoffError(error)).toBe(true);
    expect(shouldRetryQuery(0, error)).toBe(false);
    expect(shouldAutoRefetchQuery(queryWithError(error))).toBe(false);
  });

  test("keeps one retry and auto-refetch for ordinary 503 API errors", () => {
    const error = new ApiError({
      status: 503,
      code: "service_unavailable",
      detail: {
        code: "upstream_unavailable",
        message: "Try again.",
      },
    });

    expect(isRateLimitBackoffError(error)).toBe(false);
    expect(shouldRetryQuery(0, error)).toBe(true);
    expect(shouldRetryQuery(1, error)).toBe(false);
    expect(shouldAutoRefetchQuery(queryWithError(error))).toBe(true);
  });

  test("keeps one retry for transport and unexpected errors", () => {
    const error = new Error("network down");

    expect(isRateLimitBackoffError(error)).toBe(false);
    expect(shouldRetryQuery(0, error)).toBe(true);
    expect(shouldRetryQuery(1, error)).toBe(false);
    expect(shouldAutoRefetchQuery(queryWithError(error))).toBe(true);
  });

  test("keeps no-retry API statuses unchanged", () => {
    for (const status of [401, 403, 404, 422]) {
      expect(
        shouldRetryQuery(0, new ApiError({ status, code: "not_retryable", detail: null })),
      ).toBe(false);
    }
  });
});
