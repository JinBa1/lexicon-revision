import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { Footer } from "@/components/nav/Footer";
import { TopNav } from "@/components/nav/TopNav";
import { AppAuthProvider } from "@/lib/auth/runtime";
import { LANDING_HERO_COPY, PROJECT_REPOSITORY_URL } from "@/lib/publicCopy";

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

    expect(screen.getByRole("link", { name: "LEXICON REVISION" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "LEXICON REVISION" })).toHaveClass(
      "text-[14px]",
      "sm:text-[17px]",
    );
    expect(screen.getByRole("link", { name: "Supported Universities" })).toHaveClass("text-sm");
    expect(screen.getByRole("link", { name: "Supported Universities" })).not.toHaveClass(
      "uppercase",
    );
    expect(screen.getByRole("link", { name: "About" })).not.toHaveClass("uppercase");
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
  test("renders split footer links with centered repository link and bottom line", () => {
    renderWithRouter(<Footer />);

    expect(screen.getByRole("contentinfo")).toHaveClass("bg-paper-footer");
    expect(screen.getByRole("contentinfo")).toHaveClass("py-5", "sm:py-6");
    expect(screen.getByRole("navigation", { name: "Footer" })).toHaveClass(
      "sm:grid-cols-[1fr_auto_1fr]",
      "gap-3",
      "font-bold",
    );
    expect(screen.getByRole("link", { name: "Supported universities" })).toHaveAttribute(
      "href",
      "/sign-up",
    );
    expect(screen.getByRole("link", { name: "About" })).toHaveAttribute("href", "/about");
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
    expect(screen.getByRole("link", { name: "Project repository on GitHub" })).toHaveAttribute(
      "href",
      PROJECT_REPOSITORY_URL,
    );
    expect(screen.getByRole("link", { name: "Project repository on GitHub" })).toHaveClass(
      "rounded-sm",
      "border-transparent",
      "text-ink-muted",
    );
    expect(screen.getByText("© 2026 LEXICON REVISION")).toBeInTheDocument();
    expect(screen.queryByText("GH")).toBeNull();
    expect(screen.queryByText(/OPEN SOURCE/i)).toBeNull();
    expect(screen.queryByRole("link", { name: "LEXICON REVISION" })).toBeNull();
    expect(screen.queryByText(LANDING_HERO_COPY.title)).toBeNull();
    expect(screen.queryByText("abcdef1")).toBeNull();
    expect(screen.queryByText(/Est\. 2026/i)).toBeNull();
  });
});
