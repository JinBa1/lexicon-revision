import { describe, expect, test } from "vitest";

import { ApiError, isApiError } from "@/lib/api/errors";

describe("ApiError", () => {
  test("carries status, code, and detail", () => {
    const err = new ApiError({ status: 403, code: "forbidden", detail: "nope" });

    expect(err.status).toBe(403);
    expect(err.code).toBe("forbidden");
    expect(err.detail).toBe("nope");
    expect(err).toBeInstanceOf(Error);
  });

  test("isApiError narrows thrown errors", () => {
    try {
      throw new ApiError({ status: 404, code: "not_found", detail: "" });
    } catch (e) {
      expect(isApiError(e)).toBe(true);
      if (isApiError(e)) {
        expect(e.status).toBe(404);
      }
    }

    expect(isApiError(new Error("x"))).toBe(false);
  });

  test("supports FastAPI validation detail arrays", () => {
    const err = new ApiError({
      status: 422,
      code: "invalid_request",
      detail: [{ loc: ["body", "query"], msg: "Field required", type: "missing" }],
    });

    expect(err.status).toBe(422);
    expect(Array.isArray(err.detail)).toBe(true);
  });

  test("preserves object-shaped detail payloads", () => {
    const detail = { reason: "forbidden", source: "policy" };
    const err = new ApiError({
      status: 403,
      code: "forbidden",
      detail,
    });

    expect(err.detail).toEqual(detail);
    expect(err.message).toBe("forbidden");
  });
});
