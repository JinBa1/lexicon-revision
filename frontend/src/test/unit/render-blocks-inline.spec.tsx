import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InlineRuns } from "@/components/shared/render-blocks/InlineRuns";
import type { InlineRun } from "@/lib/api/types";

describe("<InlineRuns>", () => {
  it("renders text runs verbatim", () => {
    const runs: InlineRun[] = [
      { type: "text", text: "Compute " },
      { type: "text", text: "the derivative." },
    ];

    render(<InlineRuns runs={runs} />);

    expect(screen.getByText("Compute the derivative.")).toBeInTheDocument();
  });

  it("renders math runs as inline KaTeX", () => {
    const runs: InlineRun[] = [{ type: "math", latex: "x^2" }];

    const { container } = render(<InlineRuns runs={runs} />);

    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.querySelector(".katex-display")).toBeNull();
  });

  it("renders interleaved text and math runs in order", () => {
    const runs: InlineRun[] = [
      { type: "text", text: "Let " },
      { type: "math", latex: "x^2" },
      { type: "text", text: " be positive." },
    ];

    const { container } = render(<InlineRuns runs={runs} />);
    const renderedRuns = Array.from(container.childNodes);

    expect(renderedRuns).toHaveLength(3);
    expect(renderedRuns[0]?.textContent).toBe("Let ");
    expect(renderedRuns[1]).toBeInstanceOf(HTMLSpanElement);
    expect((renderedRuns[1] as HTMLElement).querySelector(".katex")).not.toBeNull();
    expect(renderedRuns[2]?.textContent).toBe(" be positive.");
    expect(container.querySelector(".katex-display")).toBeNull();
  });
});
