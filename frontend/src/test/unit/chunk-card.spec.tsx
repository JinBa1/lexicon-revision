import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, test } from "vitest";
import { ChunkCard } from "@/components/shared/ChunkCard";
import type { CollectionMetadataSchema, MediaRef, RenderBlock } from "@/lib/api/types";
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

const renderBlocksWithMathAndCode: RenderBlock[] = [
  {
    type: "paragraph",
    runs: [
      { type: "text", text: "Solve " },
      { type: "math", latex: "x^2" },
      { type: "text", text: " using dynamic programming." },
    ],
  },
  { type: "code", code: "def solve():\n    return 1", language: "python" },
];

const directMedia: MediaRef[] = [
  {
    media_id: "image_1",
    kind: "image",
    object_key: "chunks/image_1.png",
    access_url: "https://example.test/image_1.png",
    relation: "direct",
  },
  {
    media_id: "image_2",
    kind: "image",
    object_key: "chunks/image_2.png",
    access_url: "https://example.test/image_2.png",
    relation: "direct",
  },
];

describe("ChunkCard", () => {
  test("compact mode shows excerpt text", () => {
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

    // M20b: meta chips replace the slash-joined summary line
    expect(screen.getByText("Year: 2022")).toBeInTheDocument();
    expect(screen.getByText("Has figure: false")).toBeInTheDocument();
  });

  test("compact mode renders render_blocks with KaTeX and code indicator", () => {
    const { container } = render(
      <ChunkCard
        mode="compact"
        chunk={{
          chunk_id: questionResult.chunk_id,
          chunk_level: questionResult.chunk_level,
          parent_chunk_id: null,
          sub_question_label: null,
          text: "plain fallback text",
          metadata: questionResult.metadata,
          media: [],
          render_blocks: renderBlocksWithMathAndCode,
        }}
      />,
    );

    expect(container.querySelector(".katex")).not.toBeNull();
    expect(screen.getByText(/Contains code/i)).toBeInTheDocument();
    expect(screen.queryByText(/plain fallback text/i)).not.toBeInTheDocument();
  });

  test("compact mode renders fallback text and metadata indicators when render_blocks is missing", () => {
    render(
      <ChunkCard
        mode="compact"
        chunk={{
          chunk_id: questionResult.chunk_id,
          chunk_level: questionResult.chunk_level,
          parent_chunk_id: null,
          sub_question_label: null,
          text: "fallback with media metadata",
          metadata: { has_code: true, has_table: true, has_figure: true },
          media: [],
        }}
      />,
    );

    expect(screen.getByText(/fallback with media metadata/i)).toBeInTheDocument();
    expect(screen.getByText(/Contains code/i)).toBeInTheDocument();
    expect(screen.getByText(/Contains table/i)).toBeInTheDocument();
    expect(screen.getByText(/Contains figure/i)).toBeInTheDocument();
  });

  test("compact mode treats empty render_blocks as fallback for metadata indicators", () => {
    render(
      <ChunkCard
        mode="compact"
        chunk={{
          chunk_id: questionResult.chunk_id,
          chunk_level: questionResult.chunk_level,
          parent_chunk_id: null,
          sub_question_label: null,
          text: "fallback for empty blocks",
          metadata: { has_table: true },
          media: [],
          render_blocks: [],
        }}
      />,
    );

    expect(screen.getByText(/fallback for empty blocks/i)).toBeInTheDocument();
    expect(screen.getByText(/Contains table/i)).toBeInTheDocument();
  });

  test("full mode dedupes MediaList items already referenced by render blocks", () => {
    render(
      <ChunkCard
        mode="full"
        chunk={{
          chunk_id: chunkDetailFixture.chunk_id,
          chunk_level: chunkDetailFixture.chunk_level,
          parent_chunk_id: chunkDetailFixture.parent_chunk_id,
          sub_question_label: chunkDetailFixture.sub_question_label,
          text: "fallback body",
          metadata: chunkDetailFixture.metadata,
          media: directMedia,
          render_blocks: [
            { type: "paragraph", runs: [{ type: "text", text: "Body before image." }] },
            { type: "image", media_id: "image_1" },
          ],
        }}
        parent={null}
      />,
    );

    expect(screen.getAllByRole("img")).toHaveLength(2);
    expect(screen.getByRole("img", { name: "Question media 1" })).toHaveAttribute(
      "src",
      "https://example.test/image_2.png",
    );
  });

  test("full mode renders parent render_blocks instead of parent fallback text", () => {
    render(
      <ChunkCard
        mode="full"
        chunk={{
          chunk_id: chunkDetailFixture.chunk_id,
          chunk_level: chunkDetailFixture.chunk_level,
          parent_chunk_id: chunkDetailFixture.parent_chunk_id,
          sub_question_label: chunkDetailFixture.sub_question_label,
          text: "child body",
          metadata: chunkDetailFixture.metadata,
          media: [],
          render_blocks: null,
        }}
        parent={{
          text: "plain parent fallback",
          metadata: {},
          render_blocks: [
            { type: "paragraph", runs: [{ type: "text", text: "Structured parent context" }] },
          ],
        }}
      />,
    );

    expect(screen.getByText(/Structured parent context/i)).toBeInTheDocument();
    expect(screen.queryByText(/plain parent fallback/i)).not.toBeInTheDocument();
  });

  test("full mode: parent image blocks not deduplicated from MediaList (parent section has no media lookup)", () => {
    // New design: ParentCollapsible renders parent blocks without media prop,
    // so parent image blocks show "Image unavailable" inline. The image still
    // appears in MediaList since blockMediaIds only covers chunk render_blocks.
    render(
      <ChunkCard
        mode="full"
        chunk={{
          chunk_id: chunkDetailFixture.chunk_id,
          chunk_level: chunkDetailFixture.chunk_level,
          parent_chunk_id: chunkDetailFixture.parent_chunk_id,
          sub_question_label: chunkDetailFixture.sub_question_label,
          text: "child body",
          metadata: chunkDetailFixture.metadata,
          media: [
            {
              media_id: "image_parent",
              kind: "image",
              object_key: "chunks/image_parent.png",
              access_url: "https://example.test/image_parent.png",
              relation: "inherited_shared",
            },
          ],
          render_blocks: [{ type: "paragraph", runs: [{ type: "text", text: "Child body." }] }],
        }}
        parent={{
          text: "parent fallback",
          metadata: {},
          render_blocks: [{ type: "image", media_id: "image_parent" }],
        }}
      />,
    );

    // The image surfaces in MediaList (chunk.media not referenced by chunk render_blocks)
    expect(screen.getByRole("img", { name: "Question media 1" })).toHaveAttribute(
      "src",
      "https://example.test/image_parent.png",
    );
    expect(screen.getAllByRole("img")).toHaveLength(1);
  });
});

describe("<ChunkCard> compact (M20b)", () => {
  const baseChunk = {
    chunk_id: "x",
    chunk_level: "question" as const,
    parent_chunk_id: null,
    sub_question_label: null,
    text: "fallback text",
    metadata: { year: 2024, paper: 1, question: 3 },
    media: [],
    render_blocks: null,
  };

  it("base row reserves border-l-4 transparent", () => {
    const { container } = render(<ChunkCard mode="compact" chunk={baseChunk} />);
    expect((container.firstChild as HTMLElement).className).toContain("border-l-4");
    expect((container.firstChild as HTMLElement).className).toContain("border-l-transparent");
  });

  it("selected row applies .selectable-selected", () => {
    const { container } = render(
      <ChunkCard mode="compact" chunk={baseChunk} selected onClick={() => {}} />,
    );
    expect((container.firstChild as HTMLElement).className).toContain("selectable-selected");
  });

  it("renders meta chip row from exposed schema fields", () => {
    const schema = {
      version: 1,
      fields: [
        {
          key: "year",
          label: "Year",
          type: "integer" as const,
          operators: [],
          exposed: true,
          source: null,
        },
        {
          key: "paper",
          label: "Paper",
          type: "integer" as const,
          operators: [],
          exposed: true,
          source: null,
        },
      ],
    };
    render(<ChunkCard mode="compact" chunk={baseChunk} metadataSchema={schema} />);
    expect(screen.getByText(/Year/)).toBeInTheDocument();
    expect(screen.getByText(/Paper/)).toBeInTheDocument();
  });

  it("does not render the legacy '{N} media' footer", () => {
    const chunk = {
      ...baseChunk,
      media: [
        {
          media_id: "image_1",
          kind: "image" as const,
          object_key: null,
          access_url: null,
          relation: "direct" as const,
        },
      ],
    };
    render(<ChunkCard mode="compact" chunk={chunk} />);
    expect(screen.queryByText(/\d+ media/)).not.toBeInTheDocument();
  });
});

describe("<ChunkCard> full (M20b)", () => {
  const baseChunk = {
    chunk_id: "x",
    chunk_level: "sub_question" as const,
    parent_chunk_id: "p",
    sub_question_label: "a",
    text: "body",
    metadata: { year: 2024 },
    media: [],
    render_blocks: null,
  };

  it("renders section eyebrow with sub_question_label literal", () => {
    render(<ChunkCard mode="full" chunk={baseChunk} parent={null} />);
    // Spec: eyebrow text equals sub_question_label exactly ("a"), or
    // "Matched question" when null.
    expect(screen.getByText("a")).toBeInTheDocument();
  });

  it("renders 'Matched question' eyebrow when sub_question_label is null", () => {
    const chunk = { ...baseChunk, sub_question_label: null, chunk_level: "question" as const };
    render(<ChunkCard mode="full" chunk={chunk} parent={null} />);
    expect(screen.getByText("Matched question")).toBeInTheDocument();
  });

  it("renders meta chip row instead of slashed metadata", () => {
    const schema = {
      version: 1,
      fields: [
        {
          key: "year",
          label: "Year",
          type: "integer" as const,
          operators: [],
          exposed: true,
          source: null,
        },
      ],
    };
    render(<ChunkCard mode="full" chunk={baseChunk} parent={null} metadataSchema={schema} />);
    expect(screen.getByText(/Year/)).toBeInTheDocument();
  });

  it("parent block is collapsed by default and toggled by Show full parent", () => {
    const parent = { text: "long parent text", metadata: {}, render_blocks: null };
    render(<ChunkCard mode="full" chunk={baseChunk} parent={parent} />);
    const toggle = screen.getByRole("button", { name: /show full parent|collapse parent/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
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
