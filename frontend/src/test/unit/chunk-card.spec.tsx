import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { ChunkCard } from "@/components/shared/ChunkCard";
import type { CollectionMetadataSchema } from "@/lib/api/types";
import { renderMetadataSummary } from "@/lib/metadata/render";
import { chunkDetailFixture, questionResult, subQuestionResult } from "../fixtures/search";

const metadataSchema: CollectionMetadataSchema = {
  version: 1,
  fields: [
    {
      key: "paper",
      label: "Paper",
      type: "string",
      operators: ["eq"],
      exposed: true,
      source: "paper_label",
    },
    {
      key: "has_figure",
      label: "Has figure",
      type: "boolean",
      operators: ["eq"],
      exposed: true,
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
  ],
};

describe("ChunkCard", () => {
  test("compact mode shows metadata line and excerpt", () => {
    render(
      <ChunkCard
        mode="compact"
        chunk={{
          chunk_id: questionResult.chunk_id,
          chunk_level: questionResult.chunk_level,
          parent_chunk_id: null,
          sub_question_label: null,
          text: questionResult.text,
          metadata: questionResult.metadata,
          media: [],
        }}
      />,
    );
    expect(screen.getByText(/2022/)).toBeInTheDocument();
    expect(screen.getByText(/paper 5/i)).toBeInTheDocument();
    expect(screen.getByText(/amortized analysis/i)).toBeInTheDocument();
  });

  test("compact mode renders sub_question label indent affordance", () => {
    const { container } = render(
      <ChunkCard
        mode="compact"
        chunk={{
          chunk_id: subQuestionResult.chunk_id,
          chunk_level: subQuestionResult.chunk_level,
          parent_chunk_id: subQuestionResult.parent_chunk_id,
          sub_question_label: subQuestionResult.sub_question_label,
          text: subQuestionResult.text,
          metadata: subQuestionResult.metadata,
          media: [],
        }}
      />,
    );
    expect(container.firstChild).toHaveClass("ml-5");
  });

  test("compact mode renders non-interactive markup when no click handler is provided", () => {
    const { container } = render(
      <ChunkCard
        mode="compact"
        chunk={{
          chunk_id: questionResult.chunk_id,
          chunk_level: questionResult.chunk_level,
          parent_chunk_id: null,
          sub_question_label: null,
          text: questionResult.text,
          metadata: questionResult.metadata,
          media: [],
        }}
      />,
    );

    expect(container.querySelector("button")).toBeNull();
    expect(container.firstChild).toHaveClass("block");
  });

  test("compact mode keeps button behavior when a click handler is provided", () => {
    const { container } = render(
      <ChunkCard
        mode="compact"
        onClick={() => {}}
        chunk={{
          chunk_id: questionResult.chunk_id,
          chunk_level: questionResult.chunk_level,
          parent_chunk_id: null,
          sub_question_label: null,
          text: questionResult.text,
          metadata: questionResult.metadata,
          media: [],
        }}
      />,
    );

    expect(container.querySelector("button")).not.toBeNull();
  });

  test("full mode renders parent context when chunk is sub_question", () => {
    render(
      <ChunkCard
        mode="full"
        chunk={{
          chunk_id: chunkDetailFixture.chunk_id,
          chunk_level: chunkDetailFixture.chunk_level,
          parent_chunk_id: chunkDetailFixture.parent_chunk_id,
          sub_question_label: chunkDetailFixture.sub_question_label,
          text: chunkDetailFixture.text,
          metadata: chunkDetailFixture.metadata,
          media: chunkDetailFixture.media,
        }}
        parent={chunkDetailFixture.parent}
      />,
    );
    expect(screen.getByText(/Give an amortized analysis/i)).toBeInTheDocument();
    expect(screen.getByText(/halves on underflow/i)).toBeInTheDocument();
  });

  test("compact mode accepts schema-driven metadata display", () => {
    render(
      <ChunkCard
        mode="compact"
        chunk={{
          chunk_id: questionResult.chunk_id,
          chunk_level: questionResult.chunk_level,
          parent_chunk_id: null,
          sub_question_label: null,
          text: questionResult.text,
          metadata: { year: 2022, paper_label: "Paper 5", has_figure: false },
          media: [],
        }}
        metadataSchema={metadataSchema}
      />,
    );

    expect(screen.getByText("Paper 5 / No / 2022")).toBeInTheDocument();
  });
});

describe("renderMetadataSummary", () => {
  test("renders metadata in schema order using source keys and explicit booleans", () => {
    expect(
      renderMetadataSummary(
        { year: 2022, paper_label: "Paper 5", has_figure: false },
        { schema: metadataSchema },
      ),
    ).toBe("Paper 5 / No / 2022");
  });

  test("prefers schema field keys when source paths are present", () => {
    expect(
      renderMetadataSummary(
        { year: 2022, paper: 5 },
        {
          schema: {
            version: 1,
            fields: [
              {
                key: "year",
                label: "Year",
                type: "integer",
                operators: ["eq"],
                exposed: true,
                source: "chunk.year",
              },
              {
                key: "paper",
                label: "Paper",
                type: "integer",
                operators: ["eq"],
                exposed: true,
                source: "chunk.paper",
              },
            ],
          },
        },
      ),
    ).toBe("2022 / 5");
  });

  test("falls back to generic metadata when schema fields do not resolve", () => {
    expect(
      renderMetadataSummary(
        { year: 2022, paper_label: "Paper 5" },
        {
          schema: {
            version: 1,
            fields: [
              {
                key: "missing",
                label: "Missing",
                type: "string",
                operators: ["eq"],
                exposed: true,
                source: null,
              },
            ],
          },
        },
      ),
    ).toBe("paper label: Paper 5 / year: 2022");
  });

  test("falls back to deterministic generic key values when schema is unavailable", () => {
    expect(renderMetadataSummary({ year: 2022, has_figure: true, paper_label: "Paper 5" })).toBe(
      "has figure: Yes / paper label: Paper 5 / year: 2022",
    );
  });
});
