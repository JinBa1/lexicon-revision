import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { SignInRoute } from "@/routes/sign-in";

const { mockedEnv, mockSetStubHeaderEmail, mockUseAppAuth } = vi.hoisted(() => ({
  mockedEnv: {
    apiBaseUrl: "http://api.test",
    authMode: "stub_header" as const,
    stubAuthEmail: null as string | null,
    clerkPublishableKey: "pk_test_fixture",
    buildSha: "abcdef1234567890",
  },
  mockSetStubHeaderEmail: vi.fn(),
  mockUseAppAuth: vi.fn(),
}));

vi.mock("@/env", () => ({
  env: mockedEnv,
}));

vi.mock("@/lib/auth/runtime", () => ({
  useAppAuth: mockUseAppAuth,
}));

function renderSignInRoute(initialEntry = "/sign-in") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/sign-in/*" element={<SignInRoute />} />
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return (
    <div data-testid="location">
      {location.pathname}
      {location.search}
    </div>
  );
}

describe("SignInRoute", () => {
  beforeEach(() => {
    mockedEnv.authMode = "stub_header";
    mockedEnv.stubAuthEmail = null;
    mockSetStubHeaderEmail.mockReset();
    mockUseAppAuth.mockReturnValue({
      authMode: "stub_header",
      isSignedIn: false,
      stubHeaderEmail: null,
      setStubHeaderEmail: mockSetStubHeaderEmail,
    });
  });

  test("submits trimmed stub email and returns to the requested route", async () => {
    const user = userEvent.setup();
    renderSignInRoute("/sign-in?returnTo=/c/cam-cs-tripos/questions?q=trees");

    await user.type(screen.getByRole("textbox"), "  student@cam.ac.uk  ");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(mockSetStubHeaderEmail).toHaveBeenCalledWith("student@cam.ac.uk");
    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos/questions?q=trees");
  });

  test("falls back to home when stub return target is an external URL", async () => {
    const user = userEvent.setup();
    renderSignInRoute("/sign-in?returnTo=https://evil.test");

    await user.type(screen.getByRole("textbox"), "student@cam.ac.uk");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(mockSetStubHeaderEmail).toHaveBeenCalledWith("student@cam.ac.uk");
    expect(screen.getByTestId("location")).toHaveTextContent(/^\/$/);
  });

  test("falls back to home when stub return target contains a decoded backslash", async () => {
    const user = userEvent.setup();
    renderSignInRoute("/sign-in?returnTo=/%5Cevil.test");

    await user.type(screen.getByRole("textbox"), "student@cam.ac.uk");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(mockSetStubHeaderEmail).toHaveBeenCalledWith("student@cam.ac.uk");
    expect(screen.getByTestId("location")).toHaveTextContent(/^\/$/);
  });

  test("initializes the stub email from current auth state before env fallback", () => {
    mockedEnv.stubAuthEmail = "env@example.edu";
    mockUseAppAuth.mockReturnValue({
      authMode: "stub_header",
      isSignedIn: true,
      stubHeaderEmail: "current@example.edu",
      setStubHeaderEmail: mockSetStubHeaderEmail,
    });

    renderSignInRoute();

    expect(screen.getByRole("textbox")).toHaveValue("current@example.edu");
  });

  test("initializes the stub email from env fallback when no stub email is active", () => {
    mockedEnv.stubAuthEmail = "env@example.edu";

    renderSignInRoute();

    expect(screen.getByRole("textbox")).toHaveValue("env@example.edu");
  });

  test("passes return targets and routing props to Clerk sign-in mode", () => {
    mockUseAppAuth.mockReturnValue({
      authMode: "clerk",
      isSignedIn: false,
      stubHeaderEmail: null,
      setStubHeaderEmail: mockSetStubHeaderEmail,
    });

    renderSignInRoute("/sign-in?returnTo=/c/cam-cs-tripos");

    const signIn = screen.getByTestId("clerk-sign-in");
    expect(signIn).toHaveAttribute("data-routing", "path");
    expect(signIn).toHaveAttribute("data-path", "/sign-in");
    expect(signIn).toHaveAttribute("data-sign-up-url", "/sign-up?returnTo=%2Fc%2Fcam-cs-tripos");
    expect(signIn).toHaveAttribute("data-fallback-redirect-url", "/c/cam-cs-tripos");
    expect(signIn).toHaveAttribute("data-sign-up-fallback-redirect-url", "/c/cam-cs-tripos");
  });

  test("falls back to home when Clerk return target is an external URL", () => {
    mockUseAppAuth.mockReturnValue({
      authMode: "clerk",
      isSignedIn: false,
      stubHeaderEmail: null,
      setStubHeaderEmail: mockSetStubHeaderEmail,
    });

    renderSignInRoute("/sign-in?returnTo=https://evil.test");

    const signIn = screen.getByTestId("clerk-sign-in");
    expect(signIn).toHaveAttribute("data-sign-up-url", "/sign-up?returnTo=%2F");
    expect(signIn).toHaveAttribute("data-fallback-redirect-url", "/");
    expect(signIn).toHaveAttribute("data-sign-up-fallback-redirect-url", "/");
  });

  test("falls back to home when Clerk return target contains a decoded backslash", () => {
    mockUseAppAuth.mockReturnValue({
      authMode: "clerk",
      isSignedIn: false,
      stubHeaderEmail: null,
      setStubHeaderEmail: mockSetStubHeaderEmail,
    });

    renderSignInRoute("/sign-in?returnTo=/%5Cevil.test");

    const signIn = screen.getByTestId("clerk-sign-in");
    expect(signIn).toHaveAttribute("data-sign-up-url", "/sign-up?returnTo=%2F");
    expect(signIn).toHaveAttribute("data-fallback-redirect-url", "/");
    expect(signIn).toHaveAttribute("data-sign-up-fallback-redirect-url", "/");
  });
});
