import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { Footer } from "@/components/nav/Footer";
import { TopNav } from "@/components/nav/TopNav";
import { AppAuthProvider } from "@/lib/auth/runtime";

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

function renderWithRouter(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

function renderTopNav() {
  return renderWithRouter(
    <AppAuthProvider>
      <TopNav />
    </AppAuthProvider>,
  );
}

describe("TopNav", () => {
  beforeEach(() => {
    mockedEnv.authMode = "stub_header";
    mockedEnv.stubAuthEmail = null;
    window.sessionStorage.clear();
  });

  test("shows a sign-in link for anonymous users", () => {
    renderTopNav();

    expect(screen.getByRole("link", { name: "The Tripos Archive" })).toHaveAttribute("href", "/");
    const signInLink = screen.getByRole("link", { name: /sign in/i });
    expect(signInLink).toHaveAttribute("href", "/sign-in");
    expect(within(signInLink).queryByRole("button", { name: /sign in/i })).toBeNull();
  });

  test("shows the app user button for a signed-in stub user", () => {
    mockedEnv.stubAuthEmail = "student@example.edu";

    renderTopNav();

    expect(screen.queryByRole("link", { name: /sign in/i })).toBeNull();
    expect(
      screen.getByRole("button", { name: /student@example\.edu .* sign out/i }),
    ).toBeInTheDocument();
  });
});

describe("Footer", () => {
  test("renders archive links and the truncated build SHA", () => {
    renderWithRouter(<Footer />);

    expect(screen.getByRole("link", { name: "Supported universities" })).toHaveAttribute(
      "href",
      "/sign-up",
    );
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");
    expect(screen.getByText("Read the question. Then ask yours.")).toBeInTheDocument();
    expect(screen.getByText("abcdef1")).toBeInTheDocument();
  });
});
