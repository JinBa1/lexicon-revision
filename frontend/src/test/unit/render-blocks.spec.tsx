import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RenderBlocks } from "@/components/shared/render-blocks";
import sampleBlocks from "@/test/fixtures/render-blocks/sample.json";
import type { RenderBlock } from "@/lib/api/types";

const blocks = sampleBlocks as RenderBlock[];

describe("<RenderBlocks> full mode", () => {
  it("renders paragraph with inline math via KaTeX", () => {
    const { container } = render(<RenderBlocks blocks={blocks} mode="full" />);

    expect(container.querySelectorAll(".katex").length).toBeGreaterThan(0);
  });

  it("renders display equation with .katex-display", () => {
    const { container } = render(<RenderBlocks blocks={blocks} mode="full" />);

    expect(container.querySelector(".katex-display")).not.toBeNull();
  });

  it("renders table cells from rows array", () => {
    render(<RenderBlocks blocks={blocks} mode="full" />);

    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("beta")).toBeInTheDocument();
  });

  it("renders code block contents", () => {
    render(<RenderBlocks blocks={blocks} mode="full" />);

    expect(screen.getByText(/for i in range/)).toBeInTheDocument();
  });

  it("renders fallback text when blocks is null", () => {
    render(<RenderBlocks blocks={null} mode="full" fallbackText="just text" />);

    expect(screen.getByText("just text")).toBeInTheDocument();
  });

  it("renders nothing when blocks is null and no fallback", () => {
    const { container } = render(<RenderBlocks blocks={null} mode="full" />);

    expect(container.textContent).toBe("");
  });
});

describe("<RenderBlocks> compact mode", () => {
  it("emits indicator chips for code/table/image", () => {
    render(<RenderBlocks blocks={blocks} mode="compact" compactLines={3} />);

    expect(screen.getByText(/Contains code/i)).toBeInTheDocument();
    expect(screen.getByText(/Contains table/i)).toBeInTheDocument();
    expect(screen.getByText(/Contains figure/i)).toBeInTheDocument();
  });

  it("applies WebkitLineClamp to the inline container", () => {
    const { container } = render(<RenderBlocks blocks={blocks} mode="compact" compactLines={4} />);
    const clamped = container.querySelector(".question-prose-clamp");

    expect(clamped).not.toBeNull();
    expect((clamped as HTMLElement).style.webkitLineClamp).toBe("4");
  });
});
