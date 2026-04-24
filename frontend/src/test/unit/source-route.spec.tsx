import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { SourceRoute } from "@/routes/source";

import { cambridgeAccessible } from "../fixtures/collections";
import { chunkDetailFixture } from "../fixtures/search";

const { mockUseChunk, mockUseCollections } = vi.hoisted(() => ({
  mockUseChunk: vi.fn(),
  mockUseCollections: vi.fn(),
}));

vi.mock("@/lib/hooks/useChunk", () => ({
  useChunk: mockUseChunk,
}));

vi.mock("@/lib/hooks/useCollections", () => ({
  useCollections: mockUseCollections,
}));

function renderSource(initialEntry = "/c/cam-cs-tripos/source/cam-2022-p5-q3-b") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <LocationProbe />
      <Routes>
        <Route path="/c/:collection/source/:chunkId" element={<SourceRoute />} />
        <Route path="*" element={<div />} />
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

function setChunkState(overrides: Record<string, unknown> = {}) {
  const state = {
    data: chunkDetailFixture,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
  mockUseChunk.mockReturnValue(state);
  return state;
}

describe("SourceRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCollections.mockReturnValue({
      data: [cambridgeAccessible],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    setChunkState();
  });

  test("requests the route chunk and renders a prose loading skeleton", () => {
    setChunkState({ data: undefined, isLoading: true });

    const { container } = renderSource();

    expect(mockUseChunk).toHaveBeenCalledWith({
      collection: "cam-cs-tripos",
      chunkId: "cam-2022-p5-q3-b",
    });
    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(8);
  });

  test("renders the full chunk and parent context", () => {
    renderSource();

    expect(screen.getByText(/Parent question/i)).toBeInTheDocument();
    expect(screen.getByText(/Give an amortized analysis/i)).toBeInTheDocument();
    expect(screen.getByText(/halves on underflow/i)).toBeInTheDocument();
  });

  test("404 errors show source not found and navigate back to questions", async () => {
    setChunkState({
      data: undefined,
      isError: true,
      error: new ApiError({ status: 404, code: "not_found", detail: "Missing" }),
    });

    renderSource();

    expect(screen.getByRole("alert")).toHaveTextContent("Source not found");
    expect(screen.getByRole("alert")).toHaveTextContent(
      '"cam-2022-p5-q3-b" is no longer in cam-cs-tripos.',
    );

    await userEvent.click(screen.getByRole("button", { name: "Back to questions" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos/questions");
  });

  test("403 errors show access denied and navigate home", async () => {
    setChunkState({
      data: undefined,
      isError: true,
      error: new ApiError({ status: 403, code: "forbidden", detail: "Forbidden" }),
    });

    renderSource();

    expect(screen.getByRole("alert")).toHaveTextContent("Access denied");

    await userEvent.click(screen.getByRole("button", { name: "Back to home" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/");
  });

  test("generic errors retry loading the source", async () => {
    const refetch = vi.fn();
    setChunkState({
      data: undefined,
      isError: true,
      error: new Error("network down"),
      refetch,
    });

    renderSource();

    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load source");

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(refetch).toHaveBeenCalledOnce();
  });
});
