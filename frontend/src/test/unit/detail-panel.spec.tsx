import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, test } from "vitest";

import { DetailPanel } from "@/components/questions/DetailPanel";
import type { RenderBlock } from "@/lib/api/types";
import { chunkDetailFixture } from "../fixtures/search";

function renderDetailPanel(props: React.ComponentProps<typeof DetailPanel>) {
  return render(
    <MemoryRouter>
      <DetailPanel {...props} />
    </MemoryRouter>,
  );
}

describe("DetailPanel", () => {
  test("renders a prose loading skeleton while detail is loading", () => {
    const { container } = renderDetailPanel({
      collection: "cam-cs-tripos",
      collectionDisplay: "Cam Cs Tripos Fixture",
      query: "dynamic",
      rank: null,
      chunk: undefined,
      isLoading: true,
    });

    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    expect(screen.queryByText("Select a result")).not.toBeInTheDocument();
  });

  test("renders an empty prompt before a result is selected", () => {
    renderDetailPanel({
      collection: "cam-cs-tripos",
      collectionDisplay: "Cam Cs Tripos Fixture",
      query: "dynamic",
      rank: null,
      chunk: undefined,
      isLoading: false,
    });

    expect(screen.getByText("Select a result")).toBeInTheDocument();
    expect(
      screen.getByText("Pick a question on the left to see full text, metadata, and media."),
    ).toBeInTheDocument();
  });

  test("renders full chunk detail with parent context and source link", () => {
    renderDetailPanel({
      collection: "cam-cs-tripos",
      collectionDisplay: "Cam Cs Tripos Fixture",
      query: "dynamic",
      rank: 2,
      chunk: chunkDetailFixture,
      isLoading: false,
    });

    expect(screen.getByText(/Give an amortized analysis/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /halves on underflow/i })).toBeInTheDocument();

    expect(screen.getByRole("link", { name: /open shareable source/i })).toHaveAttribute(
      "href",
      "/c/cam-cs-tripos/source/cam-2022-p5-q3-b",
    );
  });

  test("passes child and parent render_blocks through to the full ChunkCard", () => {
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

    const { container } = renderDetailPanel({
      collection: "cam-cs-tripos",
      collectionDisplay: "Cam Cs Tripos Fixture",
      query: "dynamic",
      rank: 2,
      chunk: {
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
      isLoading: false,
    });

    expect(screen.getByText("Structured parent question text")).toBeInTheDocument();
    expect(screen.getAllByText(/Structured child prompt with/i).length).toBeGreaterThanOrEqual(1);
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(screen.getByText(/def answer\(\):\s+return 42/)).toBeInTheDocument();
    expect(screen.getByText("overflow")).toBeInTheDocument();
    expect(screen.queryByText("CHILD FALLBACK SHOULD NOT RENDER")).not.toBeInTheDocument();
    expect(screen.queryByText("PARENT FALLBACK SHOULD NOT RENDER")).not.toBeInTheDocument();
  });

  it("renders primary 'Open shareable source' button instead of footer link", () => {
    renderDetailPanel({
      collection: "cam",
      collectionDisplay: "Cam",
      query: "dynamic",
      rank: 1,
      chunk: chunkDetailFixture,
      isLoading: false,
    });
    expect(screen.getByRole("link", { name: /open shareable source/i })).toBeInTheDocument();
  });

  test("renders detail sections", () => {
    renderDetailPanel({
      collection: "cam-cs-tripos",
      collectionDisplay: "Cam Cs Tripos Fixture",
      query: "amortized analysis",
      rank: 1,
      chunk: chunkDetailFixture,
      isLoading: false,
    });

    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /halves on underflow/i })).toBeInTheDocument();
    expect(screen.getByText("✦ Matched")).toBeInTheDocument();
    expect(screen.queryByText("✦ Matched prompt")).not.toBeInTheDocument();
    expect(screen.getByText("Parent question")).toBeInTheDocument();
    expect(screen.getByText("Question metadata")).toBeInTheDocument();
    expect(screen.queryByText("Exam metadata")).not.toBeInTheDocument();
    expect(screen.getByText("Collection")).toBeInTheDocument();
    expect(screen.getByText("Cam Cs Tripos Fixture")).toBeInTheDocument();
    expect(screen.queryByText("Paper 5 · Question 3 · (b)")).not.toBeInTheDocument();
  });

  test("preserves source back state when opening the shareable source", async () => {
    render(
      <MemoryRouter
        initialEntries={["/c/cam-cs-tripos/questions?q=dynamic&focus=cam-2022-p5-q3-b"]}
      >
        <Routes>
          <Route
            path="/c/:collection/questions"
            element={
              <DetailPanel
                collection="cam-cs-tripos"
                collectionDisplay="Cam Cs Tripos Fixture"
                query="dynamic"
                rank={2}
                chunk={chunkDetailFixture}
                isLoading={false}
              />
            }
          />
          <Route path="/c/:collection/source/:chunkId" element={<SourceStateProbe />} />
        </Routes>
      </MemoryRouter>,
    );

    await userEvent.click(screen.getByRole("link", { name: /open shareable source/i }));

    expect(screen.getByTestId("source-state")).toHaveTextContent(
      JSON.stringify({ from: "/c/cam-cs-tripos/questions?q=dynamic&focus=cam-2022-p5-q3-b" }),
    );
  });
});

function SourceStateProbe() {
  const location = useLocation();
  return <div data-testid="source-state">{JSON.stringify(location.state)}</div>;
}
