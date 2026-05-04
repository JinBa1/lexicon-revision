import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { LANDING_HERO_COPY } from "@/lib/publicCopy";
import { LandingRoute } from "@/routes/landing";
import {
  cambridgeAccessible,
  cambridgeLocked,
  oxfordWrongAffiliation,
  publicCollection,
} from "../fixtures/collections";

const { mockUseAppAuth, mockUseCollections } = vi.hoisted(() => ({
  mockUseAppAuth: vi.fn(),
  mockUseCollections: vi.fn(),
}));

vi.mock("@/lib/auth/runtime", () => ({
  useAppAuth: mockUseAppAuth,
}));

vi.mock("@/lib/hooks/useCollections", () => ({
  useCollections: mockUseCollections,
}));

function renderLanding(initialEntry = "/") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/" element={<LandingRoute />} />
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
  refetch = vi.fn(),
}: {
  data?: unknown;
  isLoading?: boolean;
  isError?: boolean;
  refetch?: () => void;
}) {
  mockUseCollections.mockReturnValue({ data, isLoading, isError, refetch });
  return refetch;
}

describe("LandingRoute", () => {
  beforeEach(() => {
    mockUseAppAuth.mockReturnValue({ isSignedIn: false });
    setCollectionsState({ data: [publicCollection] });
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test("renders the landing hero and loading skeleton while collections load", () => {
    setCollectionsState({ isLoading: true });
    const { container } = renderLanding();

    expect(screen.getByRole("heading", { name: LANDING_HERO_COPY.title }));
    expect(screen.getByRole("region", { name: "Search workflow" })).toBeInTheDocument();
    expect(screen.getByText("Select the archive to search")).toBeInTheDocument();
    expect(screen.getByText("Enter what you want to learn")).toBeInTheDocument();
    expect(screen.getByText("Choose your next step")).toBeInTheDocument();
    expect(screen.queryByText(/Pick a collection below to enable search/i)).toBeNull();
    expect(screen.getByText(/Choose a collection below to enable search\./i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View collections ↓" })).toHaveAttribute(
      "href",
      "#collections",
    );
    expect(document.getElementById("collections")).toBeInTheDocument();
    expect(screen.getByText(LANDING_HERO_COPY.eyebrow)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pick a collection" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pick a collection" })).not.toHaveTextContent("▾");
    expect(screen.queryByRole("button", { name: "Filters" })).toBeNull();
    expect(screen.getByRole("button", { name: "Get answer with sources" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Find questions" })).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();
  });

  test("renders an error state with retry action", async () => {
    const refetch = setCollectionsState({ isError: true });

    renderLanding();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load the catalogue");
    expect(refetch).toHaveBeenCalledOnce();
  });

  test("renders the empty catalogue state", () => {
    setCollectionsState({ data: [] });

    renderLanding();

    expect(screen.getByText("No collections are available yet")).toBeInTheDocument();
    expect(screen.getByText(/sign in to see yours/i)).toBeInTheDocument();
  });

  test("navigates accessible collection picks to collection home", async () => {
    setCollectionsState({ data: [cambridgeAccessible] });

    renderLanding();
    expect(
      screen.getByRole("link", { name: "Can't find your course? Suggest a collection->" }),
    ).toHaveAttribute("href", "/sign-up");

    await userEvent.click(screen.getByRole("button", { name: /Cambridge CS Tripos/ }));

    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos");
  });

  test("preserves typed query when selecting an accessible collection", async () => {
    setCollectionsState({ data: [cambridgeAccessible] });

    renderLanding();
    await userEvent.type(screen.getByLabelText("Query"), "graph traversal");
    await userEvent.click(screen.getByRole("button", { name: /Cambridge CS Tripos/ }));

    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos?q=graph+traversal");
  });

  test("omits q when selecting an accessible collection with whitespace query", async () => {
    setCollectionsState({ data: [cambridgeAccessible] });

    renderLanding();
    await userEvent.type(screen.getByLabelText("Query"), "   ");
    await userEvent.click(screen.getByRole("button", { name: /Cambridge CS Tripos/ }));

    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos");
  });

  test("scope picker selects an accessible collection scope and preserves q", async () => {
    setCollectionsState({ data: [cambridgeAccessible] });

    renderLanding("/?scopePicker=1&page=answer&q=graph traversal");
    await userEvent.click(screen.getByRole("button", { name: /Cambridge CS Tripos/ }));

    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos?q=graph+traversal");
  });

  test("uses edited query state when scope picker selects an accessible collection scope", async () => {
    setCollectionsState({ data: [cambridgeAccessible] });

    renderLanding("/?scopePicker=1&page=answer&q=old query");
    const input = screen.getByLabelText("Query");
    await userEvent.clear(input);
    await userEvent.type(input, "edited answer query");
    await userEvent.click(screen.getByRole("button", { name: /Cambridge CS Tripos/ }));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos?q=edited+answer+query",
    );
  });

  test("navigates sign-in locked collections through unlock with return target", async () => {
    setCollectionsState({ data: [cambridgeLocked] });

    renderLanding("/?page=questions&q=binary search");
    await userEvent.click(screen.getByRole("button", { name: /Cambridge CS Tripos/ }));

    const location = screen.getByTestId("location").textContent ?? "";
    expect(location).toContain("/unlock/cam-cs-tripos?");
    expect(new URLSearchParams(location.split("?")[1]).get("returnTo")).toBe(
      "/c/cam-cs-tripos?q=binary+search",
    );
  });

  test("uses edited query state for locked collection return target", async () => {
    setCollectionsState({ data: [cambridgeLocked] });

    renderLanding("/?page=questions&q=old topic");
    const input = screen.getByLabelText("Query");
    await userEvent.clear(input);
    await userEvent.type(input, "edited locked topic");
    await userEvent.click(screen.getByRole("button", { name: /Cambridge CS Tripos/ }));

    const location = screen.getByTestId("location").textContent ?? "";
    expect(location).toContain("/unlock/cam-cs-tripos?");
    expect(new URLSearchParams(location.split("?")[1]).get("returnTo")).toBe(
      "/c/cam-cs-tripos?q=edited+locked+topic",
    );
  });

  test("shows wrong-affiliation modal in place for signed-in locked rows", async () => {
    mockUseAppAuth.mockReturnValue({ isSignedIn: true });
    setCollectionsState({ data: [cambridgeAccessible, oxfordWrongAffiliation] });

    renderLanding();
    await userEvent.click(screen.getByRole("button", { name: /Oxford Mathematics/ }));

    expect(screen.getByRole("dialog", { name: /Oxford Mathematics access mismatch/i }));
    expect(screen.queryByTestId("location")).toBeNull();
  });

  test("shows no-affiliation banner when signed in with no accessible collections", () => {
    mockUseAppAuth.mockReturnValue({ isSignedIn: true });
    setCollectionsState({ data: [cambridgeLocked, oxfordWrongAffiliation] });

    renderLanding();

    expect(screen.getByRole("status")).toHaveTextContent(
      "no collection in our catalogue is currently tied to your email domain",
    );
  });

  test("alerts and scrolls when submitting without a collection scope", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    setCollectionsState({ data: [cambridgeAccessible] });

    renderLanding();
    await userEvent.click(screen.getByRole("button", { name: /Find questions/i }));

    expect(screen.getByRole("alert")).toHaveTextContent("Please pick a collection first");
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  });

  test("keeps scope-missing alert visible until the latest timeout", async () => {
    vi.useFakeTimers();
    setCollectionsState({ data: [cambridgeAccessible] });

    renderLanding();
    fireEvent.click(screen.getByRole("button", { name: /Find questions/i }));
    await act(async () => {
      vi.advanceTimersByTime(1_000);
    });
    fireEvent.click(screen.getByRole("button", { name: /Find questions/i }));
    await act(async () => {
      vi.advanceTimersByTime(1_199);
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Please pick a collection first");

    await act(async () => {
      vi.advanceTimersByTime(1);
    });

    expect(screen.queryByRole("alert")).toBeNull();
  });
});
