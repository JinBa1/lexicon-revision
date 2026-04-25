import { beforeEach, describe, expect, test, vi } from "vitest";

describe("env", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllEnvs();
    vi.stubEnv("VITE_API_BASE_URL", "http://api.test");
    vi.stubEnv("VITE_AUTH_MODE", "stub_header");
    vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "");
    vi.stubEnv("VITE_BUILD_SHA", "test");
  });

  test("allows stub-header auth without a Clerk publishable key", async () => {
    const { env } = await import("@/env");

    expect(env.authMode).toBe("stub_header");
    expect(env.clerkPublishableKey).toBe("");
  });

  test("defaults to stub-header auth when auth mode is omitted", async () => {
    vi.unstubAllEnvs();
    vi.stubEnv("VITE_API_BASE_URL", "http://api.test");

    const { env } = await import("@/env");

    expect(env.authMode).toBe("stub_header");
  });

  test("rejects an unknown auth mode", async () => {
    vi.stubEnv("VITE_AUTH_MODE", "clrek");

    await expect(import("@/env")).rejects.toThrow(
      "VITE_AUTH_MODE must be one of: stub_header, clerk",
    );
  });

  test("requires a Clerk publishable key in Clerk auth mode", async () => {
    vi.stubEnv("VITE_AUTH_MODE", "clerk");

    await expect(import("@/env")).rejects.toThrow(
      "VITE_CLERK_PUBLISHABLE_KEY is required when VITE_AUTH_MODE=clerk",
    );
  });

  test("accepts a Clerk publishable key in Clerk auth mode", async () => {
    vi.stubEnv("VITE_AUTH_MODE", "clerk");
    vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "pk_test_fixture");

    const { env } = await import("@/env");

    expect(env.authMode).toBe("clerk");
    expect(env.clerkPublishableKey).toBe("pk_test_fixture");
  });
});
