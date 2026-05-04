import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError } from "@/lib/api/errors";
import type { CollectionListItem, RenderBlock } from "@/lib/api/types";
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

type SourceInitialEntry =
  | string
  | { pathname: string; search?: string; hash?: string; state?: unknown };

function renderSource(
  initialEntry: SourceInitialEntry = "/c/cam-cs-tripos/source/cam-2022-p5-q3-b",
) {
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
    expect(screen.getAllByText(/halves on underflow/i).length).toBeGreaterThan(0);
  });

  test("does not render header search chrome", () => {
    renderSource();

    expect(screen.queryByPlaceholderText("Enter a topic or a question…")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /find questions/i })).not.toBeInTheDocument();
  });

  test("renders shareable source panel, metadata, and copy link button without duplicating the prompt title", () => {
    setChunkState({
      data: {
        ...chunkDetailFixture,
        text: "Fallback heading should not be used",
        render_blocks: [
          {
            type: "paragraph",
            runs: [
              { type: "text", text: "First structured heading with " },
              { type: "math", latex: "x^2" },
            ],
          },
        ] satisfies RenderBlock[],
      },
    });

    renderSource();

    expect(screen.getByTestId("source-result-panel")).toHaveClass(
      "bg-paper-raised",
      "border-rule",
      "shadow-[0_12px_35px_rgba(0,0,0,0.04)]",
    );
    expect(screen.getByRole("heading", { level: 1, name: "Shareable Source" })).toHaveClass(
      "section-eyebrow",
      "tracking-[0.2em]",
      "text-claret",
    );
    expect(
      screen.queryByRole("heading", { name: "First structured heading with $x^2$" }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText(/First structured heading with/i)).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
    expect(screen.getByTestId("source-anchor-block")).toHaveClass(
      "bg-claret-active",
      "border-l-[3px]",
      "border-l-claret",
    );
  });

  test("copy link uses an absolute URL derived from the route location and origin", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: { writeText },
    });
    window.history.pushState(null, "", "/stale-window-location");

    renderSource("/c/cam-cs-tripos/source/cam-2022-p5-q3-b?from=deep#media");

    await userEvent.click(screen.getByRole("button", { name: "Copy link" }));

    expect(writeText).toHaveBeenCalledWith(
      `${window.location.origin}/c/cam-cs-tripos/source/cam-2022-p5-q3-b?from=deep#media`,
    );
    expect(writeText).not.toHaveBeenCalledWith(expect.stringContaining("stale-window-location"));
  });

  test("renders metadata chips with normalized sublabels and schema source fallback", () => {
    const collection: CollectionListItem = {
      ...cambridgeAccessible,
      metadata_schema: {
        version: 1,
        fields: [
          {
            key: "academic_year",
            label: "Year",
            type: "integer",
            operators: ["eq"],
            exposed: true,
            source: "chunk.year",
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
      },
    };
    mockUseCollections.mockReturnValue({
      data: [collection],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderSource();

    expect(screen.getByText("Part (b)")).toBeInTheDocument();
    expect(screen.getByText("2022")).toBeInTheDocument();
    expect(screen.getByText("Paper 5")).toBeInTheDocument();
  });

  test("formats source metadata chips using dotted source keys and readable values", () => {
    const collection: CollectionListItem = {
      ...cambridgeAccessible,
      metadata_schema: {
        version: 1,
        fields: [
          {
            key: "paper",
            label: "Paper",
            type: "string",
            operators: ["eq"],
            exposed: true,
            source: "paper.label",
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
            key: "question_label",
            label: "Question",
            type: "string",
            operators: ["eq"],
            exposed: true,
            source: null,
          },
          {
            key: "marks",
            label: "Marks",
            type: "integer",
            operators: ["eq"],
            exposed: true,
            source: null,
          },
          {
            key: "attrs",
            label: "Attrs",
            type: "string",
            operators: ["eq"],
            exposed: true,
            source: null,
          },
        ],
      },
    };
    mockUseCollections.mockReturnValue({
      data: [collection],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    setChunkState({
      data: {
        ...chunkDetailFixture,
        metadata: {
          "paper.label": "Paper dotted",
          has_figure: false,
          question_label: "Question 3",
          marks: 8,
          attrs: { topic: "amortized" },
        },
      },
    });

    renderSource();

    expect(screen.getByText("Paper dotted")).toBeInTheDocument();
    expect(screen.getByText("Q3")).toBeInTheDocument();
    expect(screen.getByText("8 marks")).toBeInTheDocument();
    expect(screen.getByText("Has figure: No")).toBeInTheDocument();
    expect(screen.getByText('Attrs: {"topic":"amortized"}')).toBeInTheDocument();
  });

  test("location state back target uses Back to results and navigates there", async () => {
    renderSource({
      pathname: "/c/cam-cs-tripos/source/cam-2022-p5-q3-b",
      state: { from: "/c/cam-cs-tripos/questions?q=foo" },
    });

    await userEvent.click(screen.getByRole("button", { name: "← Back to results" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos/questions?q=foo");
  });

  test("missing location state falls back to collection questions", async () => {
    renderSource();

    await userEvent.click(screen.getByRole("button", { name: "← Back to collection" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos/questions");
  });

  test("parent question is collapsed by default and toggles expanded state", async () => {
    renderSource();

    const toggle = screen.getByRole("button", { name: /Show full parent/i });
    const parentBody = screen.getByTestId("source-parent-body");

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(parentBody).toHaveClass("max-h-36", "overflow-hidden", "text-ink");

    await userEvent.click(toggle);

    expect(screen.getByRole("button", { name: /Collapse parent/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(parentBody).not.toHaveClass("max-h-36");
  });

  test("passes child and parent render_blocks through to the custom layout", async () => {
    const childBlocks: RenderBlock[] = [
      {
        type: "paragraph",
        runs: [
          { type: "text", text: "Structured child prompt with " },
          { type: "math", latex: "x^2" },
          { type: "text", text: "." },
        ],
      },
      { type: "code", code: "def answer():\n    return 42", language: "python" },
      {
        type: "table",
        rows: [
          ["Case", "Cost"],
          ["overflow", "O(1) amortized"],
        ],
        media_id: null,
      },
    ];
    const parentBlocks: RenderBlock[] = [
      {
        type: "paragraph",
        runs: [{ type: "text", text: "Structured parent question text" }],
      },
    ];

    setChunkState({
      data: {
        ...chunkDetailFixture,
        text: "CHILD FALLBACK SHOULD NOT RENDER",
        render_blocks: childBlocks,
        parent: chunkDetailFixture.parent
          ? {
              ...chunkDetailFixture.parent,
              text: "PARENT FALLBACK SHOULD NOT RENDER",
              render_blocks: parentBlocks,
            }
          : null,
      },
    });

    const { container } = renderSource();

    await userEvent.click(screen.getByRole("button", { name: /Show full parent/i }));

    expect(screen.getByText("Structured parent question text")).toBeInTheDocument();
    expect(screen.getAllByText(/Structured child prompt with/i).length).toBeGreaterThan(0);
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(screen.getByText(/def answer\(\):\s+return 42/)).toBeInTheDocument();
    expect(screen.getByText("overflow")).toBeInTheDocument();
    expect(screen.queryByText("CHILD FALLBACK SHOULD NOT RENDER")).not.toBeInTheDocument();
    expect(screen.queryByText("PARENT FALLBACK SHOULD NOT RENDER")).not.toBeInTheDocument();
  });

  test("renders media refs that are not referenced by render blocks without duplicating referenced media", () => {
    setChunkState({
      data: {
        ...chunkDetailFixture,
        media: [
          {
            media_id: "referenced-image",
            kind: "image",
            object_key: "referenced.png",
            access_url: "https://example.test/referenced.png",
            relation: "direct",
          },
          {
            media_id: "remaining-image",
            kind: "image",
            object_key: "remaining.png",
            access_url: "https://example.test/remaining.png",
            relation: "direct",
          },
          {
            media_id: "remaining-unavailable",
            kind: "image",
            object_key: null,
            access_url: null,
            relation: "direct",
          },
          {
            media_id: "remaining-table",
            kind: "table",
            object_key: "remaining.csv",
            access_url: "https://example.test/remaining.csv",
            relation: "direct",
          },
        ],
        render_blocks: [
          {
            type: "paragraph",
            runs: [{ type: "text", text: "Question with media" }],
          },
          {
            type: "image",
            media_id: "referenced-image",
          },
        ] satisfies RenderBlock[],
      },
    });

    renderSource();

    expect(screen.getAllByAltText("Question figure 1")).toHaveLength(1);
    const remainingImage = screen.getByAltText("Question media 1");
    expect(remainingImage).toHaveAttribute("src", "https://example.test/remaining.png");
    expect(remainingImage).toHaveAttribute("loading", "lazy");
    expect(remainingImage).toHaveAttribute("width", "960");
    expect(remainingImage).toHaveAttribute("height", "640");
    expect(screen.queryByAltText("Question media 2")).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /remaining-table/i })).not.toBeInTheDocument();
    expect(screen.getByText("Media unavailable")).toBeInTheDocument();
  });

  test("404 errors show source not found and navigate back to collection fallback", async () => {
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

    await userEvent.click(screen.getByRole("button", { name: "Back to collection" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos/questions");
  });

  test("404 errors use prior results label and href when route state exists", async () => {
    setChunkState({
      data: undefined,
      isError: true,
      error: new ApiError({ status: 404, code: "not_found", detail: "Missing" }),
    });

    renderSource({
      pathname: "/c/cam-cs-tripos/source/cam-2022-p5-q3-b",
      state: { from: "/c/cam-cs-tripos/questions?q=foo" },
    });

    await userEvent.click(screen.getByRole("button", { name: "Back to results" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos/questions?q=foo");
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
