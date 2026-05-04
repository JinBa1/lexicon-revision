import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import type { StudyAnswerStatus, StudyResponse } from "@/lib/api/types";
import { AnswerRoute } from "@/routes/answer";

import {
  cambridgeAccessible,
  cambridgeLocked,
  oxfordWrongAffiliation,
} from "../fixtures/collections";

const { mockUseCollections, mockUseStudy } = vi.hoisted(() => ({
  mockUseCollections: vi.fn(),
  mockUseStudy: vi.fn(),
}));

vi.mock("@/lib/hooks/useCollections", () => ({
  useCollections: mockUseCollections,
}));

vi.mock("@/lib/hooks/useStudy", () => ({
  useStudy: mockUseStudy,
}));

function renderAnswer(initialEntry = "/c/cam-cs-tripos/answer?q=dynamic") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <LocationProbe />
      <Routes>
        <Route path="/c/:collection/answer" element={<AnswerRoute />} />
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

function studyResponse(status: StudyAnswerStatus = "ok"): StudyResponse {
  return {
    schema_version: "study_answer_v2",
    request_id: "study-1",
    query: "dynamic tables",
    scope: { collection: "cam-cs-tripos" },
    answer_status: status,
    answer: {
      overview: "Dynamic tables are usually handled with a potential argument.",
      patterns: [
        {
          label: "Dynamic table resizing",
          summary: "Explain why expansion and contraction keep amortized cost bounded.",
          supporting_chunk_ids: ["chunk-1"],
        },
      ],
      limitations: ["Only one source was retrieved."],
    },
    sources: [
      {
        chunk_id: "chunk-1",
        chunk_level: "sub_question",
        parent_chunk_id: "chunk-parent",
        sub_question_label: "(b)",
        score: 0.91,
        excerpt: "A question about table doubling and halving on underflow.",
        metadata: { year: 2022, module_title: "Algorithms" },
        why_cited: "It asks for the same amortized-analysis pattern.",
        excerpt_blocks: null,
      },
    ],
    retrieval: {
      status: "ok",
      top_k: 15,
      returned_result_count: 1,
      context_budget_tokens: 4000,
      context_chunk_ids: ["chunk-1"],
      omitted_chunk_ids: [],
      truncated_chunk_ids: [],
      filters_applied: [],
      rerank: true,
    },
    planning: {
      status: "ok",
      planner_version: "planner-v1",
      original_query: "dynamic tables",
      semantic_queries: ["dynamic tables"],
      error_category: null,
      latency_ms: 12,
    },
    generation: {
      provider: "test",
      model: "fixture",
      prompt_version: "study-v2",
      temperature: 0,
      attempt_count: 1,
      citation_drops: 0,
      error_category: null,
      latency_ms: 34,
    },
  };
}

function setStudyState(overrides: Record<string, unknown> = {}) {
  const state = {
    data: studyResponse(),
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
  mockUseStudy.mockReturnValue(state);
  return state;
}

describe("AnswerRoute", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCollections.mockReturnValue({
      data: [cambridgeAccessible],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    setStudyState();
  });

  test("enables study for non-empty query even when cached collection is locked", () => {
    mockUseCollections.mockReturnValue({
      data: [cambridgeLocked],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderAnswer();

    expect(mockUseStudy).toHaveBeenCalledWith(
      expect.objectContaining({
        collection: "cam-cs-tripos",
        query: "dynamic",
        filters: [],
        enabled: true,
      }),
    );
  });

  test("delays filtered deep links while collections load, then enables backend-driven study", () => {
    mockUseCollections.mockReturnValue({
      data: [],
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    });

    const { unmount } = renderAnswer("/c/cam-cs-tripos/answer?q=dynamic&filter=year%3Agte%3A2020");

    expect(mockUseStudy).toHaveBeenCalledWith(
      expect.objectContaining({
        query: "dynamic",
        enabled: false,
      }),
    );

    unmount();
    mockUseStudy.mockClear();
    mockUseCollections.mockReturnValue({
      data: [cambridgeLocked],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderAnswer("/c/cam-cs-tripos/answer?q=dynamic&filter=year%3Agte%3A2020");

    expect(mockUseStudy).toHaveBeenCalledWith(
      expect.objectContaining({
        collection: "cam-cs-tripos",
        query: "dynamic",
        enabled: true,
      }),
    );
  });

  test("empty query disables study and renders a prompt state", () => {
    renderAnswer("/c/cam-cs-tripos/answer");

    expect(mockUseStudy).toHaveBeenCalledWith(
      expect.objectContaining({
        query: "",
        enabled: false,
      }),
    );
    expect(screen.getByText("Ask a question to generate an answer")).toBeInTheDocument();
  });

  test("renders the answer question as an eyebrow and level-one heading", () => {
    renderAnswer();

    expect(screen.getByRole("main")).toHaveClass("max-w-[1240px]", "sm:px-10");
    expect(screen.getByTestId("answer-result-panel")).toHaveClass(
      "border",
      "border-rule",
      "bg-paper-raised",
    );
    expect(screen.getByText("The Question")).toHaveClass("text-claret", "tracking-[0.2em]");
    const heading = screen.getByRole("heading", { level: 1, name: "dynamic tables" });
    expect(heading).toHaveClass("font-display", "text-[28px]", "sm:text-[34px]", "font-bold");
    expect(heading).not.toHaveClass("italic");
  });

  test("renders limitations between the answer overview and patterns", () => {
    renderAnswer();

    const overview = screen.getByText(
      "Dynamic tables are usually handled with a potential argument.",
    );
    const limitation = screen.getByText("Only one source was retrieved.");
    const pattern = screen.getByText("Dynamic table resizing");

    expect(overview.compareDocumentPosition(limitation)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(limitation.compareDocumentPosition(pattern)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  test("invalid parsed filters render invalid state without calling study", () => {
    renderAnswer("/c/cam-cs-tripos/answer?q=dynamic&filter=paper%3Aeq%3A5");

    expect(mockUseStudy).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Filters in this link aren't valid");
    expect(screen.getByRole("alert")).toHaveTextContent("paper");
    expect(screen.getByRole("main")).toContainElement(screen.getByRole("alert"));
  });

  test("keeps header filter edits draft-only until Get answer is submitted", async () => {
    renderAnswer("/c/cam-cs-tripos/answer?q=dynamic");
    const initialStudyCalls = mockUseStudy.mock.calls.length;

    await userEvent.click(screen.getByRole("button", { name: "Filters" }));
    await userEvent.type(screen.getByLabelText("Year from"), "2021");

    expect(screen.getByRole("button", { name: "Filters (1)" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos/answer?q=dynamic");
    expect(mockUseStudy).toHaveBeenCalledTimes(initialStudyCalls);

    await userEvent.click(screen.getByRole("button", { name: "Clear all" }));
    expect(screen.getByRole("button", { name: "Filters" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos/answer?q=dynamic");
    expect(mockUseStudy).toHaveBeenCalledTimes(initialStudyCalls);

    await userEvent.type(screen.getByLabelText("Year from"), "2021");
    await userEvent.click(screen.getByRole("button", { name: "Get answer with sources" }));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos/answer?q=dynamic&filter=year%3Agte%3A2021",
    );
    expect(mockUseStudy).toHaveBeenLastCalledWith(
      expect.objectContaining({
        filters: [{ field: "year", op: "gte", value: 2021 }],
      }),
    );
  });

  test("shared header can switch from answer to questions with draft filters", async () => {
    renderAnswer("/c/cam-cs-tripos/answer?q=dynamic");

    await userEvent.click(screen.getByRole("button", { name: "Filters" }));
    await userEvent.type(screen.getByLabelText("Year from"), "2021");
    await userEvent.click(screen.getByRole("button", { name: "Find questions" }));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos/questions?q=dynamic&filter=year%3Agte%3A2021",
    );
  });

  test("403 wrong-affiliation redirects to the landing explanation", () => {
    mockUseCollections.mockReturnValue({
      data: [oxfordWrongAffiliation],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    setStudyState({
      data: undefined,
      isError: true,
      error: new ApiError({ status: 403, code: "forbidden", detail: "Forbidden" }),
    });

    renderAnswer("/c/ox-maths/answer?q=dynamic");

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/?explain=wrong-affiliation&collection=ox-maths",
    );
  });

  test("422 study errors render invalid filter state", () => {
    setStudyState({
      data: undefined,
      isError: true,
      error: new ApiError({ status: 422, code: "validation_error", detail: "Bad filter" }),
    });

    renderAnswer();

    expect(screen.getByRole("alert")).toHaveTextContent("Filters in this link aren't valid");
    expect(screen.getByRole("main")).toContainElement(screen.getByRole("alert"));
  });

  test("429 study errors show a Get answer rate limit message", () => {
    setStudyState({
      data: undefined,
      isError: true,
      error: new ApiError({
        status: 429,
        code: "rate_limited",
        detail: {
          code: "rate_limited",
          message: "Too many requests. Try again later.",
        },
      }),
    });

    renderAnswer();

    expect(screen.getByRole("alert")).toHaveTextContent("Get answer limit reached");
    expect(screen.getByRole("alert")).toHaveTextContent("Try again later");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  test.each<StudyAnswerStatus>(["insufficient_evidence", "generation_failed", "retrieval_failed"])(
    "renders answer content and fallback retrieve link for %s",
    (status) => {
      setStudyState({ data: studyResponse(status) });

      renderAnswer("/c/cam-cs-tripos/answer?q=dynamic&filter=year%3Agte%3A2020");

      expect(
        screen.getByText("Dynamic tables are usually handled with a potential argument."),
      ).toBeInTheDocument();
      expect(screen.getByText("Dynamic table resizing")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /jump to source 1/i }));
      expect(screen.getByText("2022")).toBeInTheDocument();
      expect(screen.getByText("Part (b)")).toBeInTheDocument();
      expect(screen.getByText("Why cited")).toBeInTheDocument();
      expect(
        screen.getByText("It asks for the same amortized-analysis pattern."),
      ).toBeInTheDocument();
      const fallbackLink = screen.getByRole("link", {
        name: "Retrieve matching questions instead →",
      });
      expect(fallbackLink).toHaveAttribute(
        "href",
        "/c/cam-cs-tripos/questions?q=dynamic&filter=year%3Agte%3A2020",
      );
      expect(fallbackLink.closest("div")).toHaveClass(
        "bg-paper-raised",
        "border-rule",
        "rounded-[4px]",
      );
    },
  );

  test("citation click scrolls and animates the matching source", async () => {
    const scrollIntoView = vi.fn();
    const animate = vi.fn(() => ({ finished: Promise.resolve() }) as unknown as Animation);
    const originalScrollIntoView = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "scrollIntoView",
    );
    const originalAnimate = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "animate");
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    Object.defineProperty(HTMLElement.prototype, "animate", {
      configurable: true,
      value: animate,
    });
    const addClass = vi.spyOn(DOMTokenList.prototype, "add");

    try {
      renderAnswer();

      await userEvent.click(screen.getByRole("button", { name: /jump to source 1/i }));
      const sourceCard = screen
        .getByText("A question about table doubling and halving on underflow.")
        .closest("li");

      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "center" });
      expect(addClass).toHaveBeenCalledWith("citation-highlighted");
      expect(animate).toHaveBeenCalledWith(
        expect.arrayContaining([expect.objectContaining({ boxShadow: "0 0 0 2px #7E2E2E" })]),
        expect.objectContaining({ duration: 900, easing: "ease-out" }),
      );
      await Promise.resolve();
      expect(sourceCard).not.toHaveClass("citation-highlighted");
    } finally {
      if (originalScrollIntoView) {
        Object.defineProperty(HTMLElement.prototype, "scrollIntoView", originalScrollIntoView);
      } else {
        delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView;
      }
      if (originalAnimate) {
        Object.defineProperty(HTMLElement.prototype, "animate", originalAnimate);
      } else {
        delete (HTMLElement.prototype as { animate?: unknown }).animate;
      }
      addClass.mockRestore();
    }
  });

  test("citation fallback highlight keeps the latest activation until its timeout completes", () => {
    vi.useFakeTimers();
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "scrollIntoView",
    );
    const originalAnimate = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "animate");
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    delete (HTMLElement.prototype as { animate?: unknown }).animate;

    try {
      renderAnswer();
      const citation = screen.getByRole("button", { name: /jump to source 1/i });
      const sourceCard = screen
        .getByText("A question about table doubling and halving on underflow.")
        .closest("li");

      fireEvent.click(citation);
      expect(sourceCard).toHaveClass("citation-highlighted");

      vi.advanceTimersByTime(500);
      fireEvent.click(citation);
      vi.advanceTimersByTime(500);
      expect(sourceCard).toHaveClass("citation-highlighted");

      vi.advanceTimersByTime(400);
      expect(sourceCard).not.toHaveClass("citation-highlighted");
    } finally {
      vi.useRealTimers();
      if (originalScrollIntoView) {
        Object.defineProperty(HTMLElement.prototype, "scrollIntoView", originalScrollIntoView);
      } else {
        delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView;
      }
      if (originalAnimate) {
        Object.defineProperty(HTMLElement.prototype, "animate", originalAnimate);
      } else {
        delete (HTMLElement.prototype as { animate?: unknown }).animate;
      }
    }
  });
});
