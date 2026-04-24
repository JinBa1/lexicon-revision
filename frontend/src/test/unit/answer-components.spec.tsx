import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { AnswerBody } from "@/components/answer/AnswerBody";
import { AnswerStatusBanner } from "@/components/answer/AnswerStatusBanner";
import { LimitationsBlock } from "@/components/answer/LimitationsBlock";
import { PatternsList } from "@/components/answer/PatternsList";
import { RetrievalFooter } from "@/components/answer/RetrievalFooter";
import { SourcesGrid } from "@/components/answer/SourcesGrid";
import type {
  CollectionMetadataSchema,
  StudyAnswerStatus,
  StudyPattern,
  StudyRetrieval,
  StudySource,
} from "@/lib/api/types";

const retrieval: StudyRetrieval = {
  status: "ok",
  top_k: 8,
  returned_result_count: 3,
  context_budget_tokens: 4000,
  context_chunk_ids: ["chunk-1"],
  omitted_chunk_ids: [],
  truncated_chunk_ids: [],
  filters_applied: [{ field: "year", op: "gte", value: 2020 }],
  rerank: true,
};

const source: StudySource = {
  chunk_id: "cam-2022-p5-q3-b",
  chunk_level: "sub_question",
  parent_chunk_id: "cam-2022-p5-q3",
  sub_question_label: "(b)",
  score: 0.91,
  excerpt:
    "Extend the amortized analysis to the case where the table halves on underflow, explaining the potential function and why each operation remains bounded.",
  metadata: {
    module_title: "Algorithms",
    paper_label: "Paper 5",
    question_label: "Question 3",
  },
  why_cited: "Shows the exact dynamic-table variant discussed in the answer.",
};

const metadataSchema: CollectionMetadataSchema = {
  version: 1,
  fields: [
    {
      key: "question_label",
      label: "Question",
      type: "string",
      operators: ["eq"],
      exposed: true,
      source: null,
    },
    {
      key: "module_title",
      label: "Module",
      type: "string",
      operators: ["eq"],
      exposed: false,
      source: null,
    },
    {
      key: "paper",
      label: "Paper",
      type: "string",
      operators: ["eq"],
      exposed: true,
      source: "paper_label",
    },
  ],
};

describe("AnswerBody", () => {
  test("renders the answer section with preserved prose", () => {
    const { container } = render(<AnswerBody overview={"First line.\nSecond line."} />);
    const paragraph = container.querySelector("p");

    expect(screen.getByText("Answer")).toBeInTheDocument();
    expect(paragraph).toHaveClass("whitespace-pre-wrap");
    expect(paragraph?.textContent).toBe("First line.\nSecond line.");
  });
});

describe("PatternsList", () => {
  test("renders pattern citations only for known source positions", async () => {
    const onCitationActivate = vi.fn();
    const patterns: StudyPattern[] = [
      {
        label: "Dynamic tables",
        summary: "Questions often ask for aggregate or potential-method analysis.",
        supporting_chunk_ids: ["chunk-1", "missing", "chunk-3"],
      },
    ];

    render(
      <PatternsList
        patterns={patterns}
        chunkIdToPosition={
          new Map([
            ["chunk-1", 1],
            ["chunk-3", 3],
          ])
        }
        onCitationActivate={onCitationActivate}
      />,
    );

    expect(screen.getByText("Patterns")).toBeInTheDocument();
    expect(screen.getByText("Dynamic tables")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /citation 1, view source chunk-1/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /missing/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /citation 3, view source chunk-3/i }));

    expect(onCitationActivate).toHaveBeenCalledWith("chunk-3");
  });
});

describe("LimitationsBlock", () => {
  test("renders limitations when present and nothing when empty", () => {
    const { container, rerender } = render(
      <LimitationsBlock limitations={["Only three sources were retrieved."]} />,
    );

    expect(screen.getByText("Limitations")).toBeInTheDocument();
    expect(screen.getByText("Only three sources were retrieved.")).toBeInTheDocument();

    rerender(<LimitationsBlock limitations={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});

describe("RetrievalFooter", () => {
  test("toggles retrieval diagnostics", async () => {
    render(<RetrievalFooter retrieval={retrieval} />);

    const toggle = screen.getByRole("button", { name: /3 past-paper questions retrieved/i });

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("top_k: 8")).not.toBeInTheDocument();

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("top_k: 8")).toBeInTheDocument();
    expect(screen.getByText("rerank: true")).toBeInTheDocument();
    expect(screen.getByText(/filters_applied:/)).toHaveTextContent('"field":"year"');
    expect(screen.getByText("top_k: 8").parentElement).toHaveAttribute(
      "id",
      toggle.getAttribute("aria-controls"),
    );
  });
});

describe("SourcesGrid", () => {
  test("falls back to generic metadata when no schema is provided", () => {
    const registerRef = vi.fn();

    render(
      <MemoryRouter>
        <SourcesGrid
          collection="cam-cs-tripos"
          sources={[source]}
          highlightedChunkId={source.chunk_id}
          registerRef={registerRef}
        />
      </MemoryRouter>,
    );

    expect(
      screen.getByText(
        "1 · module title: Algorithms / paper label: Paper 5 / question label: Question 3 / (b)",
      ),
    ).toBeInTheDocument();
  });

  test("renders source metadata in schema order using only exposed fields", () => {
    const registerRef = vi.fn();

    render(
      <MemoryRouter>
        <SourcesGrid
          collection="cam-cs-tripos"
          sources={[source]}
          highlightedChunkId={source.chunk_id}
          metadataSchema={metadataSchema}
          registerRef={registerRef}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("1 · Question 3 / Paper 5 / (b)")).toBeInTheDocument();
    expect(screen.queryByText(/Algorithms/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/Why cited: Shows the exact dynamic-table variant/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view source/i })).toHaveAttribute(
      "href",
      "/c/cam-cs-tripos/source/cam-2022-p5-q3-b",
    );
    expect(registerRef).toHaveBeenCalledWith(source.chunk_id, expect.any(HTMLElement));
  });
});

describe("AnswerStatusBanner", () => {
  test("hides ok status", () => {
    const { container } = render(<AnswerStatusBanner status="ok" />);

    expect(container).toBeEmptyDOMElement();
  });

  test.each<[StudyAnswerStatus, string]>([
    ["partial", "Partial answer — see limitations."],
    [
      "insufficient_evidence",
      "Insufficient evidence — consider retrieving matching questions instead.",
    ],
    ["generation_failed", "The answer service is temporarily unavailable."],
    ["retrieval_failed", "Retrieval failed. Try broadening filters or switching collection."],
  ])("shows exact copy for %s status", (status, copy) => {
    render(<AnswerStatusBanner status={status} />);

    expect(screen.getByText(copy)).toBeInTheDocument();
  });
});
