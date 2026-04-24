import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { UnlockRoute } from "@/routes/unlock";
import {
  cambridgeAccessible,
  cambridgeLocked,
  oxfordWrongAffiliation,
  publicCollection,
} from "../fixtures/collections";

const { mockUseAppAuth, mockUseCollections, mockUseSupportedUniversities } = vi.hoisted(() => ({
  mockUseAppAuth: vi.fn(),
  mockUseCollections: vi.fn(),
  mockUseSupportedUniversities: vi.fn(),
}));

vi.mock("@/lib/auth/runtime", () => ({
  useAppAuth: mockUseAppAuth,
}));

vi.mock("@/lib/hooks/useCollections", () => ({
  useCollections: mockUseCollections,
}));

vi.mock("@/lib/hooks/useSupportedUniversities", () => ({
  useSupportedUniversities: mockUseSupportedUniversities,
}));

function renderUnlockRoute(initialEntry = "/unlock/cam-cs-tripos") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/unlock/:collection" element={<UnlockRoute />} />
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

function setCollectionsState({
  data,
  isLoading = false,
  isError = false,
  isFetching = false,
  refetch = vi.fn(),
}: {
  data?: unknown;
  isLoading?: boolean;
  isError?: boolean;
  isFetching?: boolean;
  refetch?: () => void;
}) {
  mockUseCollections.mockReturnValue({ data, isLoading, isError, isFetching, refetch });
  return refetch;
}

function setUniversitiesState({
  data,
  isLoading = false,
  isError = false,
}: {
  data?: unknown;
  isLoading?: boolean;
  isError?: boolean;
}) {
  mockUseSupportedUniversities.mockReturnValue({ data, isLoading, isError });
}

describe("UnlockRoute", () => {
  beforeEach(() => {
    mockUseAppAuth.mockReturnValue({ isSignedIn: false });
    setCollectionsState({ data: [cambridgeLocked, publicCollection, oxfordWrongAffiliation] });
    setUniversitiesState({
      data: [{ id: "c-cam", display_name: "Cambridge", email_domains: ["cam.ac.uk"] }],
    });
  });

  test("renders anonymous unlock bridge with university and return target CTAs", () => {
    renderUnlockRoute("/unlock/cam-cs-tripos?returnTo=/c/cam-cs-tripos/questions?q=trees");

    expect(
      screen.getByRole("heading", {
        name: "Cambridge CS Tripos is restricted to Cambridge members.",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Use your/)).toHaveTextContent("Use your @cam.ac.uk email to sign up.");
    expect(screen.getByRole("link", { name: "Sign up with cam.ac.uk email" })).toHaveAttribute(
      "href",
      "/sign-up?university=c-cam&returnTo=%2Fc%2Fcam-cs-tripos%2Fquestions%3Fq%3Dtrees",
    );
    expect(screen.getByRole("link", { name: "Sign in to an existing account" })).toHaveAttribute(
      "href",
      "/sign-in?returnTo=%2Fc%2Fcam-cs-tripos%2Fquestions%3Fq%3Dtrees",
    );
    expect(
      screen.getByRole("link", { name: "Not at Cambridge? Browse supported universities ->" }),
    ).toHaveAttribute("href", "/sign-up");
  });

  test("omits email-domain hint when the community is not supported", () => {
    setUniversitiesState({ data: [] });

    renderUnlockRoute();

    expect(screen.queryByText(/@cam\.ac\.uk/)).toBeNull();
    expect(screen.getByRole("link", { name: "Sign up with Cambridge email" })).toHaveAttribute(
      "href",
      "/sign-up?university=c-cam&returnTo=%2Fc%2Fcam-cs-tripos",
    );
  });

  test("redirects signed-in wrong-affiliation users to the catalogue explanation", () => {
    mockUseAppAuth.mockReturnValue({ isSignedIn: true });

    renderUnlockRoute("/unlock/ox-maths");

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/?explain=wrong-affiliation&collection=ox-maths",
    );
  });

  test("redirects signed-in accessible users to the return target", () => {
    mockUseAppAuth.mockReturnValue({ isSignedIn: true });
    setCollectionsState({ data: [cambridgeAccessible] });

    renderUnlockRoute("/unlock/cam-cs-tripos?returnTo=/c/cam-cs-tripos/questions?q=trees");

    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos/questions?q=trees");
  });

  test("redirects anonymous accessible public collections to the return target", () => {
    setCollectionsState({ data: [publicCollection] });

    renderUnlockRoute("/unlock/public-demo?returnTo=/c/public-demo/questions?q=graphs");

    expect(screen.getByTestId("location")).toHaveTextContent("/c/public-demo/questions?q=graphs");
  });

  test("refetches and shows loading for signed-in stale requires-signin data", async () => {
    mockUseAppAuth.mockReturnValue({ isSignedIn: true });
    const refetch = setCollectionsState({ data: [cambridgeLocked] });

    renderUnlockRoute("/unlock/cam-cs-tripos");

    expect(screen.queryByRole("heading", { name: /restricted to Cambridge members/i })).toBeNull();
    expect(screen.getByRole("main").querySelector('[aria-busy="true"]')).toBeInTheDocument();
    await waitFor(() => expect(refetch).toHaveBeenCalledOnce());
  });

  test("renders an error state for missing collections", () => {
    renderUnlockRoute("/unlock/not-real");

    expect(screen.getByRole("alert")).toHaveTextContent("Collection not found");
    expect(screen.getByText('"not-real" is not in the catalogue.')).toBeInTheDocument();
  });
});
