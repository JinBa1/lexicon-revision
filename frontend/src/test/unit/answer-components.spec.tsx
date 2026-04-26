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
    year: 2024,
  },
  why_cited: "Shows the exact dynamic-table variant discussed in the answer.",
  excerpt_blocks: null,
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
      key: "year",
      label: "Year",
      type: "integer",
      operators: ["eq", "gte", "lte"],
      exposed: true,
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
    expect(screen.getByRole("button", { name: /jump to source 1/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /missing/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /jump to source 3/i }));

    expect(onCitationActivate).toHaveBeenCalledWith("chunk-3");
  });
});

describe("LimitationsBlock", () => {
  test("renders nothing when empty", () => {
    const { container } = render(<LimitationsBlock limitations={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  test("renders limitations in a bordered callout", () => {
    render(
      <LimitationsBlock
        limitations={["Only three sources were retrieved.", "The answer may omit later papers."]}
      />,
    );

    const callout = screen.getByRole("complementary", { name: /limitations/i });

    expect(screen.getByText("Limitations")).toBeInTheDocument();
    expect(screen.getByText("Only three sources were retrieved.")).toBeInTheDocument();
    expect(screen.getByText("The answer may omit later papers.")).toBeInTheDocument();
    expect(callout).toHaveClass("border-l-4", "border-claret");
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
  test("renders excerpt_blocks with inline math in compact mode", () => {
    const registerRef = vi.fn();
    const sourceWithMath: StudySource = {
      ...source,
      excerpt: "Fallback text should not render when blocks are present.",
      excerpt_blocks: [
        {
          type: "paragraph",
          runs: [
            { type: "text", text: "Use potential " },
            { type: "math", latex: "\\Phi=n" },
            { type: "text", text: " for amortized cost." },
          ],
        },
      ],
    };

    const { container } = render(
      <MemoryRouter>
        <SourcesGrid
          collection="cam-cs-tripos"
          sources={[sourceWithMath]}
          highlightedChunkId={source.chunk_id}
          registerRef={registerRef}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText(/Use potential/i)).toBeInTheDocument();
    expect(screen.queryByText(/Fallback text should not render/i)).not.toBeInTheDocument();
    expect(container.querySelectorAll(".katex").length).toBeGreaterThan(0);
    expect(container.querySelector(".question-prose-clamp")).toHaveStyle({
      WebkitLineClamp: "4",
    });
  });

  test("renders excerpt_blocks table indicator in compact mode", () => {
    const registerRef = vi.fn();
    const sourceWithTable: StudySource = {
      ...source,
      excerpt_blocks: [
        {
          type: "table",
          rows: [
            ["operation", "cost"],
            ["insert", "O(1) amortized"],
          ],
          media_id: null,
        },
      ],
    };

    render(
      <MemoryRouter>
        <SourcesGrid
          collection="cam-cs-tripos"
          sources={[sourceWithTable]}
          highlightedChunkId={source.chunk_id}
          registerRef={registerRef}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText(/Contains table/i)).toBeInTheDocument();
  });

  test("renders fallback excerpt text when excerpt_blocks is null", () => {
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

    expect(screen.getByText(source.excerpt)).toBeInTheDocument();
  });

  test("renders only the sub-question metadata chip when no schema is provided", () => {
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

    expect(screen.getByText("Part (b)")).toBeInTheDocument();
    expect(screen.queryByText(/module title:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/paper label:/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/question label:/i)).not.toBeInTheDocument();
  });

  test("renders source metadata as schema-ordered chips using only exposed fields", () => {
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

    expect(screen.getByText("Part (b)")).toBeInTheDocument();
    expect(screen.getByText("Question: Question 3")).toBeInTheDocument();
    expect(screen.getByText("Year: 2024")).toBeInTheDocument();
    expect(screen.getByText("Paper: Paper 5")).toBeInTheDocument();
    expect(screen.queryByText(/Question 3 \/ 2024 \/ Paper 5/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Algorithms/)).not.toBeInTheDocument();
    expect(screen.getByText("Why cited")).toBeInTheDocument();
    expect(screen.getByText(source.why_cited as string)).toBeInTheDocument();
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

  test("shows warm caution treatment for partial answers", () => {
    const { container } = render(<AnswerStatusBanner status="partial" />);
    const banner = container.firstElementChild;

    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText("Partial answer")).toHaveClass("font-bold");
    expect(
      screen.getByText("Some sub-questions had no strong evidence — see Limitations below."),
    ).toHaveClass("mt-1");
    expect(banner).toHaveClass(
      "bg-paper-raised",
      "border",
      "border-rule",
      "border-l-4",
      "border-l-claret",
      "text-ink",
    );
  });

  test("shows stronger warning treatment for insufficient evidence", () => {
    const { container } = render(<AnswerStatusBanner status="insufficient_evidence" />);
    const banner = container.firstElementChild;

    expect(screen.getByText("Insufficient evidence")).toBeInTheDocument();
    expect(
      screen.getByText("Try retrieving matching questions instead, or broaden your filters."),
    ).toBeInTheDocument();
    expect(banner).toHaveClass(
      "bg-claret-soft",
      "border",
      "border-claret",
      "border-l-4",
      "border-l-claret",
      "text-ink",
    );
  });

  test.each<[StudyAnswerStatus, string, string]>([
    [
      "generation_failed",
      "Could not generate answer",
      "The answer service is temporarily unavailable. Try again in a moment.",
    ],
    [
      "retrieval_failed",
      "Retrieval failed",
      "Try broadening your filters or switching collection.",
    ],
  ])("shows exact title and body copy for %s status", (status, title, body) => {
    render(<AnswerStatusBanner status={status} />);

    expect(screen.getByText(title)).toBeInTheDocument();
    expect(screen.getByText(body)).toBeInTheDocument();
  });
});
