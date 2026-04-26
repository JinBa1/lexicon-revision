import { render, screen } from "@testing-library/react";
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
        selectedChunkId={null}
        onSelect={() => {}}
        metadataSchema={null}
      />,
    );

    expect(screen.getByRole("heading", { name: /Top 1 results/i })).toBeInTheDocument();
  });

  test("renders plural match count", () => {
    render(
      <ResultList
        results={[questionResult, subQuestionResult]}
        selectedChunkId={null}
        onSelect={() => {}}
        metadataSchema={null}
      />,
    );

    expect(screen.getByRole("heading", { name: /Top 2 results/i })).toBeInTheDocument();
  });

  test("marks the selected row and selects rows by chunk id", async () => {
    const onSelect = vi.fn();

    render(
      <ResultList
        results={[questionResult, subQuestionResult]}
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
        selectedChunkId={null}
        onSelect={() => {}}
        metadataSchema={null}
      />,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
    expect(screen.getByText(/Contains code/i)).toBeInTheDocument();
    expect(screen.queryByText(/plain fallback text/i)).not.toBeInTheDocument();
  });

  it("renders 'Top {N} results' from results.length", () => {
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
        selectedChunkId={null}
        onSelect={() => {}}
        metadataSchema={null}
      />,
    );
    expect(screen.getByRole("heading", { name: /Top 2 results/i })).toBeInTheDocument();
  });
});
