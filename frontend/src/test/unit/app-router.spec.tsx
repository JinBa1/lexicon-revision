import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { App } from "@/App";

const { mockedEnv } = vi.hoisted(() => ({
  mockedEnv: {
    apiBaseUrl: "http://api.test",
    authMode: "stub_header" as const,
    stubAuthEmail: null as string | null,
    clerkPublishableKey: "pk_test_fixture",
    buildSha: "abcdef1234567890",
  },
}));

vi.mock("@/env", () => ({
  env: mockedEnv,
}));

function renderAppAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App />);
}

describe("App router", () => {
  beforeEach(() => {
    mockedEnv.stubAuthEmail = null;
    window.sessionStorage.clear();
  });

  test("renders the nav and footer shell around the landing route", () => {
    renderAppAt("/");

    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Footer" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "The Tripos Archive" })).toBeInTheDocument();
    expect(screen.getByText("landing")).toBeInTheDocument();
    expect(screen.getByText("Read the question. Then ask yours.")).toBeInTheDocument();
  });

  test("renders collection routes from dynamic paths", () => {
    renderAppAt("/c/cam-cs-tripos/questions");

    expect(screen.getByText("questions")).toBeInTheDocument();
  });

  test("renders not found content instead of redirecting unknown routes", () => {
    renderAppAt("/missing-route");

    expect(screen.getByRole("heading", { name: "Not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to home" })).toHaveAttribute("href", "/");
  });
});
