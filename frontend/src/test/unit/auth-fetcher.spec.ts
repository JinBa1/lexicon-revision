import { afterAll, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import type { ApiFetchOptions, JsonValue } from "@/lib/api/fetcher";
import { apiFetch } from "@/lib/api/fetcher";

const { mockedEnv } = vi.hoisted(() => ({
  mockedEnv: {
    apiBaseUrl: "http://api.test",
    authMode: "stub_header" as const,
    stubAuthEmail: null,
    clerkPublishableKey: "pk_test_fixture",
    buildSha: "test",
  },
}));

vi.mock("@/env", () => ({
  env: mockedEnv,
}));

const originalFetch = globalThis.fetch;

function mockResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  });
}

describe("apiFetch", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
    mockedEnv.apiBaseUrl = "http://api.test";
  });

  test("attaches bearer token when auth headers provide authorization", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(mockResponse({ ok: true }));
    const getAuthHeaders = vi.fn().mockResolvedValue({
      authorization: "Bearer token-123",
    });

    await apiFetch({ path: "/ping", getAuthHeaders });

    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get("authorization")).toBe("Bearer token-123");
  });

  test("attaches stub-header auth when configured", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(mockResponse({ ok: true }));
    const getAuthHeaders = vi.fn().mockResolvedValue({
      "X-User-Email": "student@example.edu",
    });

    await apiFetch({ path: "/ping", getAuthHeaders });

    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get("X-User-Email")).toBe("student@example.edu");
  });

  test("builds request URLs robustly for paths without a leading slash", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(mockResponse({ ok: true }));

    await apiFetch({ path: "collections", getAuthHeaders: async () => ({}) });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://api.test/collections");
  });

  test("preserves base-path prefixes for slash and non-slash paths", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock
      .mockResolvedValueOnce(mockResponse({ ok: true }))
      .mockResolvedValueOnce(mockResponse({ ok: true }));
    mockedEnv.apiBaseUrl = "https://example.com/api/";

    await apiFetch({ path: "collections", getAuthHeaders: async () => ({}) });
    await apiFetch({ path: "/collections", getAuthHeaders: async () => ({}) });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("https://example.com/api/collections");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("https://example.com/api/collections");
  });

  test("defaults to POST when body is present and method is omitted", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(mockResponse({ ok: true }));

    await apiFetch({
      path: "/search",
      body: { query: "binary search" },
      getAuthHeaders: async () => ({}),
    });

    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(
      JSON.stringify({ query: "binary search" }),
    );
  });

  test("rejects an explicit GET request body before calling fetch", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;

    await expect(
      apiFetch({
        path: "/search",
        method: "GET" as const,
        body: { query: "binary search" } as never,
        getAuthHeaders: async () => ({}),
      }),
    ).rejects.toMatchObject({
      status: 400,
      code: "invalid_request",
    });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("throws ApiError with parsed detail on 4xx/5xx", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "nope" }), {
        status: 403,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(
      apiFetch({ path: "/x", getAuthHeaders: async () => ({}) }),
    ).rejects.toMatchObject({
      status: 403,
      detail: "nope",
    });
  });

  test("preserves short text detail from non-json error bodies", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(
      new Response("Forbidden by policy", {
        status: 403,
        headers: { "content-type": "text/plain" },
      }),
    );

    await expect(
      apiFetch({ path: "/x", getAuthHeaders: async () => ({}) }),
    ).rejects.toMatchObject({
      status: 403,
      code: "forbidden",
      detail: "Forbidden by policy",
    });
  });

  test("throws ApiError with parsed detail on 5xx", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "backend offline" }), {
        status: 503,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(
      apiFetch({ path: "/x", getAuthHeaders: async () => ({}) }),
    ).rejects.toMatchObject({
      status: 503,
      code: "service_unavailable",
      detail: "backend offline",
    });
  });

  test("normalizes rejected fetch calls into a network ApiError", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(
      apiFetch({ path: "/x", getAuthHeaders: async () => ({}) }),
    ).rejects.toMatchObject({
      status: 0,
      code: "network_error",
      detail: "Failed to fetch",
    });
  });

  test("normalizes aborted fetch calls into an aborted-request ApiError", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockRejectedValue(new DOMException("The operation was aborted.", "AbortError"));

    await expect(
      apiFetch({ path: "/x", getAuthHeaders: async () => ({}) }),
    ).rejects.toMatchObject({
      status: 0,
      code: "request_aborted",
      detail: "The operation was aborted.",
    });
  });

  test("treats Error instances named AbortError as aborted requests", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    const abortError = new Error("The operation was aborted.");
    abortError.name = "AbortError";
    fetchMock.mockRejectedValue(abortError);

    await expect(
      apiFetch({ path: "/x", getAuthHeaders: async () => ({}) }),
    ).rejects.toMatchObject({
      status: 0,
      code: "request_aborted",
      detail: "The operation was aborted.",
    });
  });

  test("normalizes JSON serialization failures into an invalid-request ApiError", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    const circular = {} as Record<string, unknown>;
    circular.self = circular;

    await expect(
      apiFetch({
        path: "/x",
        body: circular as unknown as JsonValue,
        getAuthHeaders: async () => ({}),
      }),
    ).rejects.toMatchObject({
      status: 400,
      code: "invalid_request",
    });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("preserves structured 422 detail arrays", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: [{ loc: ["body", "query"], msg: "Field required", type: "missing" }],
        }),
        {
          status: 422,
          headers: { "content-type": "application/json" },
        },
      ),
    );

    await expect(
      apiFetch({ path: "/x", getAuthHeaders: async () => ({}) }),
    ).rejects.toMatchObject({
      status: 422,
      code: "invalid_request",
      detail: [{ loc: ["body", "query"], msg: "Field required", type: "missing" }],
    });
  });

  test("401 triggers redirect-to-signin side effect via onUnauthorized", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(new Response("", { status: 401 }));
    const onUnauthorized = vi.fn();

    await expect(
      apiFetch({
        path: "/x",
        getAuthHeaders: async () => ({ authorization: "Bearer t" }),
        onUnauthorized,
      }),
    ).rejects.toBeInstanceOf(ApiError);

    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  test("throws 401 ApiError even when onUnauthorized callback throws", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(new Response("", { status: 401 }));

    await expect(
      apiFetch({
        path: "/x",
        getAuthHeaders: async () => ({ authorization: "Bearer t" }),
        onUnauthorized: () => {
          throw new Error("redirect failed");
        },
      }),
    ).rejects.toMatchObject({
      status: 401,
      code: "unauthorized",
    });
  });

  test("throws 401 ApiError even when onUnauthorized callback rejects asynchronously", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(new Response("", { status: 401 }));
    const onUnauthorized = vi.fn().mockRejectedValue(new Error("redirect failed"));

    await expect(
      apiFetch({
        path: "/x",
        getAuthHeaders: async () => ({ authorization: "Bearer t" }),
        onUnauthorized,
      }),
    ).rejects.toMatchObject({
      status: 401,
      code: "unauthorized",
    });

    await Promise.resolve();
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  test("throws stable ApiError when a 200 response body is empty", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(new Response("", { status: 200 }));

    await expect(
      apiFetch({ path: "/x", getAuthHeaders: async () => ({}) }),
    ).rejects.toMatchObject({
      status: 200,
      code: "invalid_response",
    });
  });

  test("throws stable ApiError when a 200 response body is non-JSON", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(
      new Response("ok", {
        status: 200,
        headers: { "content-type": "text/plain" },
      }),
    );

    await expect(
      apiFetch({ path: "/x", getAuthHeaders: async () => ({}) }),
    ).rejects.toMatchObject({
      status: 200,
      code: "invalid_response",
    });
  });

  test("returns undefined for 204 success responses", async () => {
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await expect(
      apiFetch({ path: "/x", getAuthHeaders: async () => ({}) }),
    ).resolves.toBeUndefined();
  });
});

const validJsonBody = {
  query: "graphs",
  filters: ["2024", true, null],
} satisfies JsonValue;

expectTypeOf(validJsonBody).toMatchTypeOf<JsonValue>();

const validJsonOptions: ApiFetchOptions = {
  path: "/x",
  method: "POST",
  body: validJsonBody,
  getAuthHeaders: async () => ({}),
};

expectTypeOf(validJsonOptions).toMatchTypeOf<ApiFetchOptions>();

const invalidFormDataOptions: ApiFetchOptions = {
  path: "/x",
  method: "POST",
  // @ts-expect-error FormData bodies are intentionally not accepted by apiFetch.
  body: new FormData(),
  getAuthHeaders: async () => ({}),
};

void invalidFormDataOptions;

afterAll(() => {
  globalThis.fetch = originalFetch;
});
