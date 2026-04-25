import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { CollectionHomeRoute } from "@/routes/collection-home";
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

function renderCollectionHome(initialEntry = "/c/cam-cs-tripos") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <CurrentLocationProbe />
      <Routes>
        <Route path="/c/:collection" element={<CollectionHomeRoute />} />
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

function CurrentLocationProbe() {
  const location = useLocation();
  return (
    <div data-testid="current-location">
      {location.pathname}
      {location.search}
    </div>
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

describe("CollectionHomeRoute", () => {
  beforeEach(() => {
    mockUseAppAuth.mockReturnValue({ isSignedIn: false });
    setCollectionsState({ data: [cambridgeAccessible, publicCollection] });
    Element.prototype.scrollIntoView = vi.fn();
  });

  test("renders a loading skeleton while the catalogue loads", () => {
    setCollectionsState({ isLoading: true });
    const { container } = renderCollectionHome();

    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();
  });

  test("renders an error state with retry action", async () => {
    const refetch = setCollectionsState({ isError: true });

    renderCollectionHome();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load the catalogue");
    expect(refetch).toHaveBeenCalledOnce();
  });

  test("renders not found state for an unknown collection name", async () => {
    renderCollectionHome("/c/not-real");

    expect(screen.getByRole("alert")).toHaveTextContent("Collection not found");
    expect(screen.getByText('"not-real" is not in the catalogue.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Back to home" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/");
  });

  test("renders active collection hero and active scope card", () => {
    renderCollectionHome();

    expect(
      screen.getByRole("heading", { level: 1, name: "Cambridge CS Tripos" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cambridge CS Tripos ▾" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cambridge CS Tripos\. Active scope/ }));
    expect(screen.getByText("● Active scope")).toBeInTheDocument();
  });

  test("submits to questions with query and filters", async () => {
    renderCollectionHome("/c/cam-cs-tripos?q=graph+theory");

    await userEvent.click(screen.getByRole("button", { name: "+ Filters" }));
    await userEvent.type(screen.getByLabelText("Year from"), "2021");
    expect(screen.getByRole("button", { name: "+ Filters (1)" })).toBeInTheDocument();
    expect(screen.getByTestId("current-location")).toHaveTextContent(
      "/c/cam-cs-tripos?q=graph+theory",
    );

    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.getByTestId("current-location")).toHaveTextContent(
      "/c/cam-cs-tripos?q=graph+theory",
    );

    await userEvent.click(screen.getByRole("button", { name: "Find questions" }));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos/questions?q=graph+theory&filter=year%3Agte%3A2021",
    );
  });

  test("submits to answer with edited query", async () => {
    renderCollectionHome("/c/cam-cs-tripos?q=old query");

    const input = screen.getByLabelText("Query");
    await userEvent.clear(input);
    await userEvent.type(input, "dynamic programming");
    await userEvent.click(screen.getByRole("button", { name: "Get answer with sources" }));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos/answer?q=dynamic+programming",
    );
  });

  test("helper example clicks submit with the helper label instead of stale query state", async () => {
    renderCollectionHome("/c/cam-cs-tripos?q=previous topic");

    await userEvent.click(screen.getByRole("button", { name: "binary search" }));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos/questions?q=binary+search",
    );
  });

  test("scope switching preserves query and clears filters on collection home", async () => {
    setCollectionsState({ data: [cambridgeAccessible, publicCollection] });
    renderCollectionHome("/c/cam-cs-tripos?page=questions&q=tree rotations");

    await userEvent.click(screen.getByRole("button", { name: "+ Filters" }));
    await userEvent.type(screen.getByLabelText("Year from"), "2020");
    expect(screen.getByRole("button", { name: "+ Filters (1)" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /MIT 6\.006/ }));

    expect(screen.getByTestId("current-location")).toHaveTextContent(
      "/c/public-demo?q=tree+rotations",
    );
  });

  test("scope switching uses edited query state and omits blank q", async () => {
    setCollectionsState({ data: [cambridgeAccessible, publicCollection] });
    renderCollectionHome("/c/cam-cs-tripos?q=old topic");

    const input = screen.getByLabelText("Query");
    await userEvent.clear(input);
    await userEvent.type(input, "   ");
    await userEvent.click(screen.getByRole("button", { name: /MIT 6\.006/ }));

    expect(screen.getByTestId("current-location")).toHaveTextContent("/c/public-demo");
  });

  test("redirects collection URLs that require sign-in to unlock", () => {
    setCollectionsState({ data: [cambridgeLocked] });

    renderCollectionHome("/c/cam-cs-tripos?page=answer&q=sorting");

    const location = screen.getByTestId("location").textContent ?? "";
    expect(location).toContain("/unlock/cam-cs-tripos?");
    expect(new URLSearchParams(location.split("?")[1]).get("returnTo")).toBe(
      "/c/cam-cs-tripos?q=sorting",
    );
  });

  test("redirects wrong-affiliation collection URLs to the catalogue explanation", () => {
    setCollectionsState({ data: [oxfordWrongAffiliation] });

    renderCollectionHome("/c/ox-maths");

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/?explain=wrong-affiliation&collection=ox-maths",
    );
  });

  test("routes locked card picks to unlock with intended target", async () => {
    setCollectionsState({ data: [publicCollection, cambridgeLocked] });
    renderCollectionHome("/c/public-demo?page=questions&q=binary search");

    await userEvent.click(screen.getByRole("button", { name: /Cambridge CS Tripos/ }));

    const location = screen.getByTestId("location").textContent ?? "";
    expect(location).toContain("/unlock/cam-cs-tripos?");
    expect(new URLSearchParams(location.split("?")[1]).get("returnTo")).toBe(
      "/c/cam-cs-tripos?q=binary+search",
    );
  });

  test("shows wrong-affiliation modal for locked card picks", async () => {
    mockUseAppAuth.mockReturnValue({ isSignedIn: true });
    setCollectionsState({ data: [cambridgeAccessible, oxfordWrongAffiliation] });

    renderCollectionHome();
    await userEvent.click(screen.getByRole("button", { name: /Oxford Mathematics/ }));

    expect(screen.getByRole("dialog", { name: /Oxford Mathematics access mismatch/i }));
    expect(screen.queryByTestId("location")).toBeNull();
  });
});
