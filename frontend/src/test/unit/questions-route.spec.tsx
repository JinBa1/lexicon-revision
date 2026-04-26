import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, test, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { ApiError } from "@/lib/api/errors";
import { QuestionsRoute } from "@/routes/questions";
import {
  cambridgeAccessible,
  cambridgeLocked,
  oxfordWrongAffiliation,
} from "../fixtures/collections";
import { chunkDetailFixture, questionResult, subQuestionResult } from "../fixtures/search";

const { mockUseChunk, mockUseCollections, mockUseSearch } = vi.hoisted(() => ({
  mockUseChunk: vi.fn(),
  mockUseCollections: vi.fn(),
  mockUseSearch: vi.fn(),
}));

vi.mock("@/lib/hooks/useCollections", () => ({
  useCollections: mockUseCollections,
}));

vi.mock("@/lib/hooks/useSearch", () => ({
  useSearch: mockUseSearch,
}));

vi.mock("@/lib/hooks/useChunk", () => ({
  useChunk: mockUseChunk,
}));

function renderQuestions(initialEntry = "/c/cam-cs-tripos/questions?q=dynamic") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <LocationProbe />
      <Routes>
        <Route path="/c/:collection/questions" element={<QuestionsRoute />} />
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

function setSearchState(overrides: Record<string, unknown> = {}) {
  const state = {
    data: {
      query: "dynamic",
      collection: "cam-cs-tripos",
      results: [questionResult, subQuestionResult],
      total: 2,
    },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
  mockUseSearch.mockReturnValue(state);
  return state;
}

describe("QuestionsRoute", () => {
  beforeEach(() => {
    mockUseCollections.mockReturnValue({
      data: [cambridgeAccessible],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    setSearchState();
    mockUseChunk.mockReturnValue({
      data: chunkDetailFixture,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    });
  });

  test("does not gate search on cached collection accessibility when query is non-empty", () => {
    mockUseCollections.mockReturnValue({
      data: [cambridgeLocked],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderQuestions();

    expect(mockUseSearch).toHaveBeenCalledWith(
      expect.objectContaining({
        collection: "cam-cs-tripos",
        query: "dynamic",
        enabled: true,
      }),
    );
  });

  test("invalid parsed filters render invalid state without enabling search", () => {
    renderQuestions("/c/cam-cs-tripos/questions?q=dynamic&filter=paper%3Aeq%3A5");

    expect(mockUseSearch).toHaveBeenCalledWith(expect.objectContaining({ enabled: false }));
    expect(screen.getByRole("alert")).toHaveTextContent("Filters in this link aren't valid");
    expect(screen.getByRole("alert")).toHaveTextContent("paper");
  });

  test("keeps header filter edits draft-only until Find questions is submitted", async () => {
    renderQuestions("/c/cam-cs-tripos/questions?q=dynamic&focus=cam-2022-p5-q3");
    const initialSearchCalls = mockUseSearch.mock.calls.length;

    await userEvent.click(screen.getByRole("button", { name: "+ Filters" }));
    await userEvent.type(screen.getByLabelText("Year from"), "2021");

    expect(screen.getByRole("button", { name: "+ Filters (1)" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos/questions?q=dynamic&focus=cam-2022-p5-q3",
    );
    expect(mockUseSearch).toHaveBeenCalledTimes(initialSearchCalls);

    await userEvent.click(screen.getByRole("button", { name: "Clear all" }));
    expect(screen.getByRole("button", { name: "+ Filters" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos/questions?q=dynamic&focus=cam-2022-p5-q3",
    );
    expect(mockUseSearch).toHaveBeenCalledTimes(initialSearchCalls);

    await userEvent.type(screen.getByLabelText("Year from"), "2021");
    await userEvent.click(screen.getByRole("button", { name: "Find questions" }));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos/questions?q=dynamic&filter=year%3Agte%3A2021",
    );
    expect(screen.getByTestId("location")).not.toHaveTextContent("focus=");
    expect(mockUseSearch).toHaveBeenLastCalledWith(
      expect.objectContaining({
        filters: [{ field: "year", op: "gte", value: 2021 }],
      }),
    );
  });

  test("loading results shows row skeletons", () => {
    setSearchState({ data: undefined, isLoading: true });

    const { container } = renderQuestions();

    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThanOrEqual(3);
  });

  test("empty results render empty state and switch collection preserves query", async () => {
    setSearchState({
      data: { query: "dynamic", collection: "cam-cs-tripos", results: [], total: 0 },
    });

    renderQuestions("/c/cam-cs-tripos/questions?q=dynamic");

    expect(screen.getByText(/No past-paper questions match this query/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Switch collection" }));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/?scopePicker=1&page=questions&q=dynamic",
    );
  });

  test("generic search errors show retry action", async () => {
    const refetch = vi.fn();
    setSearchState({
      data: undefined,
      isError: true,
      error: new Error("network down"),
      refetch,
    });

    renderQuestions();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load matching questions");
    expect(refetch).toHaveBeenCalledOnce();
  });

  test("403 access revoked shows a back home action", async () => {
    setSearchState({
      data: undefined,
      isError: true,
      error: new ApiError({ status: 403, code: "forbidden", detail: "Forbidden" }),
    });

    renderQuestions();
    expect(screen.getByRole("alert")).toHaveTextContent("Access to this collection changed");

    await userEvent.click(screen.getByRole("button", { name: "Back to home" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/");
  });

  test("403 wrong-affiliation redirects to the landing explanation", () => {
    mockUseCollections.mockReturnValue({
      data: [oxfordWrongAffiliation],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    setSearchState({
      data: undefined,
      isError: true,
      error: new ApiError({ status: 403, code: "forbidden", detail: "Forbidden" }),
    });

    renderQuestions("/c/ox-maths/questions?q=dynamic");

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/?explain=wrong-affiliation&collection=ox-maths",
    );
  });

  test("422 search errors render invalid filter state", () => {
    setSearchState({
      data: undefined,
      isError: true,
      error: new ApiError({ status: 422, code: "validation_error", detail: "Bad filter" }),
    });

    renderQuestions();

    expect(screen.getByRole("alert")).toHaveTextContent("Filters in this link aren't valid");
  });

  test("row click updates focus in URL and mobile panel can clear it", async () => {
    renderQuestions();

    await userEvent.click(screen.getByRole("button", { name: /halves on underflow/i }));

    expect(screen.getByTestId("location")).toHaveTextContent("focus=cam-2022-p5-q3-b");

    await userEvent.click(screen.getByRole("button", { name: "← Back to results" }));

    expect(screen.getByTestId("location")).not.toHaveTextContent("focus=");
  });

  test("deep link with focus requests matching chunk detail", () => {
    renderQuestions("/c/cam-cs-tripos/questions?q=dynamic&focus=cam-2022-p5-q3-b");

    expect(mockUseChunk).toHaveBeenCalledWith({
      collection: "cam-cs-tripos",
      chunkId: "cam-2022-p5-q3-b",
    });
  });

  test("clears stale focus when returned results do not include the focused chunk", async () => {
    renderQuestions("/c/cam-cs-tripos/questions?q=dynamic&focus=missing");

    expect(await screen.findByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos/questions?q=dynamic",
    );
    expect(mockUseChunk).not.toHaveBeenLastCalledWith({
      collection: "cam-cs-tripos",
      chunkId: "missing",
    });
  });

  it("renders keyboard hint with Esc-only-mobile copy", () => {
    setSearchState();
    renderQuestions();

    expect(
      screen.getByText(
        /Use ↑↓ to move through results · Enter to open source · Esc to close detail \(mobile\)/i,
      ),
    ).toBeInTheDocument();
  });

  it("ArrowDown updates focus param via keyboard hook", async () => {
    setSearchState();
    renderQuestions("/c/cam-cs-tripos/questions?q=dynamic&focus=cam-2022-p5-q3");

    fireEvent.keyDown(window, { key: "ArrowDown" });

    expect(screen.getByTestId("location")).toHaveTextContent("focus=cam-2022-p5-q3-b");
  });
});
