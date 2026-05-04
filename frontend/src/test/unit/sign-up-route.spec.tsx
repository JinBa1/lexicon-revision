import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { SignUpRoute } from "@/routes/sign-up";
import type { SupportedUniversity } from "@/lib/api/types";

const { mockedEnv, mockSetStubHeaderEmail, mockUseAppAuth, mockUseSupportedUniversities } =
  vi.hoisted(() => ({
    mockedEnv: {
      apiBaseUrl: "http://api.test",
      authMode: "stub_header" as const,
      stubAuthEmail: null as string | null,
      clerkPublishableKey: "pk_test_fixture",
      buildSha: "abcdef1234567890",
    },
    mockSetStubHeaderEmail: vi.fn(),
    mockUseAppAuth: vi.fn(),
    mockUseSupportedUniversities: vi.fn(),
  }));

const universities: SupportedUniversity[] = [
  {
    id: "cambridge",
    display_name: "University of Cambridge",
    email_domains: ["cam.ac.uk"],
  },
  {
    id: "mit",
    display_name: "MIT",
    email_domains: ["mit.edu"],
  },
];

vi.mock("@/env", () => ({
  env: mockedEnv,
}));

vi.mock("@/lib/auth/runtime", () => ({
  useAppAuth: mockUseAppAuth,
}));

vi.mock("@/lib/hooks/useSupportedUniversities", () => ({
  useSupportedUniversities: mockUseSupportedUniversities,
}));

function renderSignUpRoute(initialEntry = "/sign-up") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/sign-up/*" element={<SignUpRoute />} />
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

describe("SignUpRoute", () => {
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
    mockUseSupportedUniversities.mockReturnValue({
      data: universities,
      isLoading: false,
      isError: false,
    });
  });

  test("shows four card skeletons while supported universities load", () => {
    mockUseSupportedUniversities.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });

    const { container } = renderSignUpRoute();

    expect(container.querySelector("[aria-busy='true']")).toBeInTheDocument();
    expect(container.querySelectorAll(".h-28")).toHaveLength(4);
  });

  test("shows an error when supported universities cannot be loaded", () => {
    mockUseSupportedUniversities.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });

    renderSignUpRoute();

    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load supported universities");
  });

  test("preserves sanitized returnTo when continuing from the university gate", async () => {
    const user = userEvent.setup();
    renderSignUpRoute("/sign-up?university=cambridge&returnTo=/c/cam-cs-tripos/questions?q=trees");

    expect(
      screen.getByRole("heading", { name: "Join your student community" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Supported communities")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Continue →" }));

    expect(screen.getByRole("textbox")).toHaveAttribute("placeholder", "you@cam.ac.uk");
  });

  test("falls back to home when gate returnTo is an external URL", async () => {
    const user = userEvent.setup();
    renderSignUpRoute("/sign-up?university=cambridge&returnTo=https://evil.test");

    await user.click(screen.getByRole("button", { name: "Continue →" }));
    await user.type(screen.getByRole("textbox"), "student@cam.ac.uk");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(mockSetStubHeaderEmail).toHaveBeenCalledWith("student@cam.ac.uk");
    expect(screen.getByTestId("location")).toHaveTextContent(/^\/$/);
  });

  test("submits trimmed stub email and returns to the requested app path", async () => {
    const user = userEvent.setup();
    renderSignUpRoute("/sign-up/create?university=cambridge&returnTo=/c/cam-cs-tripos");

    await user.type(screen.getByRole("textbox"), "  student@cam.ac.uk  ");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(mockSetStubHeaderEmail).toHaveBeenCalledWith("student@cam.ac.uk");
    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos");
  });

  test("initializes stub email from current auth state before env fallback", () => {
    mockedEnv.stubAuthEmail = "env@example.edu";
    mockUseAppAuth.mockReturnValue({
      authMode: "stub_header",
      isSignedIn: true,
      stubHeaderEmail: "current@example.edu",
      setStubHeaderEmail: mockSetStubHeaderEmail,
    });

    renderSignUpRoute("/sign-up/create?university=cambridge");

    expect(screen.getByRole("textbox")).toHaveValue("current@example.edu");
  });

  test("renders Clerk sign-up with path routing and sanitized redirect props", () => {
    mockUseAppAuth.mockReturnValue({
      authMode: "clerk",
      isSignedIn: false,
      stubHeaderEmail: null,
      setStubHeaderEmail: mockSetStubHeaderEmail,
    });

    renderSignUpRoute("/sign-up/create?university=cambridge&returnTo=/c/cam-cs-tripos");

    expect(screen.getByText(/Use your/i)).toHaveTextContent("@cam.ac.uk");
    const signUp = screen.getByTestId("clerk-sign-up");
    expect(signUp).toHaveAttribute("data-routing", "path");
    expect(signUp).toHaveAttribute("data-path", "/sign-up/create");
    expect(signUp).toHaveAttribute("data-sign-in-url", "/sign-in?returnTo=%2Fc%2Fcam-cs-tripos");
    expect(signUp).toHaveAttribute("data-force-redirect-url", "/c/cam-cs-tripos");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  test("forces sanitized returnTo over an unsafe Clerk redirect_url query param", () => {
    mockUseAppAuth.mockReturnValue({
      authMode: "clerk",
      isSignedIn: false,
      stubHeaderEmail: null,
      setStubHeaderEmail: mockSetStubHeaderEmail,
    });

    renderSignUpRoute(
      "/sign-up/create?university=cambridge&returnTo=/c/cam-cs-tripos&redirect_url=https://evil.test",
    );

    const signUp = screen.getByTestId("clerk-sign-up");
    expect(signUp).toHaveAttribute("data-sign-in-url", "/sign-in?returnTo=%2Fc%2Fcam-cs-tripos");
    expect(signUp).toHaveAttribute("data-force-redirect-url", "/c/cam-cs-tripos");
    expect(signUp).not.toHaveAttribute("data-force-redirect-url", "https://evil.test");
  });

  test("falls back to home when Clerk return target contains a decoded backslash", () => {
    mockUseAppAuth.mockReturnValue({
      authMode: "clerk",
      isSignedIn: false,
      stubHeaderEmail: null,
      setStubHeaderEmail: mockSetStubHeaderEmail,
    });

    renderSignUpRoute("/sign-up/create?university=cambridge&returnTo=/%5Cevil.test");

    const signUp = screen.getByTestId("clerk-sign-up");
    expect(signUp).toHaveAttribute("data-sign-in-url", "/sign-in?returnTo=%2F");
    expect(signUp).toHaveAttribute("data-force-redirect-url", "/");
  });

  test("lets the user select a different university before continuing", async () => {
    const user = userEvent.setup();
    renderSignUpRoute("/sign-up?university=cambridge&returnTo=/");

    const mitCard = screen.getByRole("button", { name: /MIT/i });
    await user.click(mitCard);
    await user.click(screen.getByRole("button", { name: "Continue →" }));

    expect(within(screen.getByRole("main")).getByRole("textbox")).toHaveAttribute(
      "placeholder",
      "you@mit.edu",
    );
  });
});
