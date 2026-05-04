import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { ResultList } from "@/components/questions/ResultList";
import type { RenderBlock, SearchResult } from "@/lib/api/types";
import { questionResult, subQuestionResult } from "../fixtures/search";

const renderBlocksWithMathAndCode: RenderBlock[] = [
  {
    type: "paragraph",
    runs: [
      { type: "text", text: "Solve " },
      { type: "math", latex: "x^2" },
      { type: "text", text: " with recurrence expansion." },
    ],
  },
  { type: "code", code: "def solve():\n    return 1", language: "python" },
];

describe("ResultList", () => {
  test("renders singular match count", () => {
    render(
      <ResultList
        results={[questionResult]}
        total={1}
        selectedChunkId={null}
        onSelect={() => {}}
        metadataSchema={null}
      />,
    );

    expect(screen.getByRole("heading", { name: "1 matching question" })).toBeInTheDocument();
    expect(screen.getByText("Ranked by relevance to your query")).toBeInTheDocument();
  });

  test("renders plural match count", () => {
    render(
      <ResultList
        results={[questionResult, subQuestionResult]}
        total={2}
        selectedChunkId={null}
        onSelect={() => {}}
        metadataSchema={null}
      />,
    );

    expect(screen.getByRole("heading", { name: "2 matching questions" })).toBeInTheDocument();
  });

  test("marks the selected row and selects rows by chunk id", async () => {
    const onSelect = vi.fn();

    render(
      <ResultList
        results={[questionResult, subQuestionResult]}
        total={2}
        selectedChunkId={subQuestionResult.chunk_id}
        onSelect={onSelect}
        metadataSchema={null}
      />,
    );

    expect(screen.getByRole("button", { name: /halves on underflow/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /amortized analysis/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    await userEvent.click(screen.getByRole("button", { name: /amortized analysis/i }));

    expect(onSelect).toHaveBeenCalledWith(questionResult.chunk_id);
  });

  test("passes result render_blocks into compact ChunkCard", () => {
    const { container } = render(
      <ResultList
        results={[
          {
            ...questionResult,
            text: "plain fallback text",
            render_blocks: renderBlocksWithMathAndCode,
          },
        ]}
        total={1}
        selectedChunkId={null}
        onSelect={() => {}}
        metadataSchema={null}
      />,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
    expect(screen.getByText(/Contains code/i)).toBeInTheDocument();
    expect(screen.queryByText(/plain fallback text/i)).not.toBeInTheDocument();
  });

  it("renders matching question count from total when provided", () => {
    const results: SearchResult[] = [
      {
        chunk_id: "a",
        chunk_level: "question" as const,
        parent_chunk_id: null,
        sub_question_label: null,
        text: "First result text",
        score: 0.9,
        metadata: {
          year: 2022,
          paper_label: "Paper 1",
          question_label: "Question 1",
          has_figure: false,
        },
        media: [],
        render_blocks: null,
      },
      {
        chunk_id: "b",
        chunk_level: "question" as const,
        parent_chunk_id: null,
        sub_question_label: null,
        text: "Second result text",
        score: 0.85,
        metadata: {
          year: 2023,
          paper_label: "Paper 2",
          question_label: "Question 2",
          has_figure: false,
        },
        media: [],
        render_blocks: null,
      },
    ];
    render(
      <ResultList
        results={results}
        total={15}
        selectedChunkId={null}
        onSelect={() => {}}
        metadataSchema={null}
      />,
    );
    expect(screen.getByRole("heading", { name: "15 matching questions" })).toBeInTheDocument();
  });

  test("renders rank circles, truthful level context, compact metadata, and selected styling", () => {
    render(
      <ResultList
        results={[questionResult, subQuestionResult]}
        total={2}
        selectedChunkId={subQuestionResult.chunk_id}
        onSelect={() => {}}
        metadataSchema={null}
      />,
    );

    expect(screen.getByText("1")).toHaveClass("rounded-full");
    expect(screen.getByText("2")).toHaveClass("rounded-full");
    expect(screen.getByText("Q")).toHaveClass("bg-claret", "text-white");
    expect(screen.getByText("Part")).toHaveClass("bg-claret-soft", "text-claret");
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.queryByText("Q 3")).not.toBeInTheDocument();
    expect(screen.getByText("b - Q 3")).toBeInTheDocument();
    expect(screen.queryByText("Paper 5 · Question 3")).not.toBeInTheDocument();
    expect(screen.queryByText("Paper: Paper 5")).not.toBeInTheDocument();
    expect(screen.queryByText("Question: Question 3")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /halves on underflow/i })).toHaveClass(
      "bg-[#F2E4DE]",
    );
  });

  test("renders level context from deployed-style question metadata", () => {
    render(
      <ResultList
        results={[
          {
            ...questionResult,
            metadata: { year: 2023, question: 2, marks: 8 },
          },
          {
            ...subQuestionResult,
            sub_question_label: "D",
            metadata: { year: 2025, question: 8, marks: 2 },
          },
        ]}
        total={2}
        selectedChunkId={null}
        onSelect={() => {}}
        metadataSchema={null}
      />,
    );

    const questionRow = screen.getByRole("button", { name: /amortized analysis/i });
    expect(within(questionRow).getByText("2")).toBeInTheDocument();
    expect(screen.queryByText("Q 2")).not.toBeInTheDocument();
    expect(screen.getByText("D - Q 8")).toBeInTheDocument();
  });
});
