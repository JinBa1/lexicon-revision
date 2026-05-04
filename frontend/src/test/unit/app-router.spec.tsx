import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { App } from "@/App";
import { cambridgeAccessible } from "../fixtures/collections";

const { mockedEnv, mockUseCollections } = vi.hoisted(() => ({
  mockedEnv: {
    apiBaseUrl: "http://api.test",
    authMode: "stub_header" as const,
    stubAuthEmail: null as string | null,
    clerkPublishableKey: "pk_test_fixture",
    buildSha: "abcdef1234567890",
  },
  mockUseCollections: vi.fn(),
}));

vi.mock("@/env", () => ({
  env: mockedEnv,
}));

vi.mock("@/lib/hooks/useCollections", () => ({
  useCollections: mockUseCollections,
}));

function renderAppAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<App />);
}

describe("App router", () => {
  beforeEach(() => {
    mockedEnv.stubAuthEmail = null;
    mockUseCollections.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    window.sessionStorage.clear();
  });

  test("renders the nav and footer shell around the landing route", () => {
    renderAppAt("/");

    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Footer" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "LEXICON REVISION" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Read the question\.\s*Then ask yours\./i }),
    ).toBeInTheDocument();
  });

  test("renders collection routes from dynamic paths", () => {
    renderAppAt("/c/cam-cs-tripos/questions");

    expect(screen.getByText("Search for a question pattern")).toBeInTheDocument();
  });

  test("renders collection home routes from dynamic paths", () => {
    mockUseCollections.mockReturnValue({
      data: [cambridgeAccessible],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderAppAt("/c/cam-cs-tripos");

    expect(
      screen.getByRole("heading", { level: 1, name: /Read the question\.\s*Then ask yours\./i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cambridge CS Tripos" })).toBeInTheDocument();
  });

  test("renders the privacy notice route", () => {
    renderAppAt("/privacy");

    expect(screen.getByRole("heading", { name: "Privacy notice" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Back to home" })).toHaveAttribute("href", "/");
    expect(screen.queryByText("Launch scaffold")).not.toBeInTheDocument();
    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByText("0.1 · draft")).toBeInTheDocument();
    expect(screen.getByText("Last updated")).toBeInTheDocument();
    expect(screen.getByText("4 May 2026")).toBeInTheDocument();
    expect(screen.getByTestId("doc-content-panel")).toHaveClass("bg-paper-raised", "border-rule");
    expect(screen.getByRole("heading", { name: "Controller and contact" })).toBeInTheDocument();
  });

  test("renders the about route as a document page", () => {
    renderAppAt("/about");

    expect(screen.getByRole("heading", { name: "About" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Back to home" })).toHaveAttribute("href", "/");
    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByTestId("doc-content-panel")).toHaveClass("bg-paper-raised", "border-rule");
  });

  test("renders not found content instead of redirecting unknown routes", () => {
    renderAppAt("/missing-route");

    expect(screen.getByRole("heading", { name: "Not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to home" })).toHaveAttribute("href", "/");
  });
});
