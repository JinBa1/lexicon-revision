import { render, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { SteppedRibbon } from "@/components/hero/SteppedRibbon";

describe("SteppedRibbon", () => {
  test("renders the three workflow steps with claret numbered badges", () => {
    render(<SteppedRibbon />);

    const list = screen.getByRole("list");

    for (const [number, label, detail] of [
      ["1", "Choose collection", "Select the archive to search"],
      ["2", "Ask a topic or question", "Enter what you want to learn"],
      ["3", "Get results", "Choose your next step"],
    ] as const) {
      const item = within(list).getByText(label).closest("li");

      expect(item).toBeInTheDocument();
      expect(item).toHaveClass("justify-start");
      expect(item).not.toHaveClass("md:justify-center");
      expect(item).not.toHaveClass("md:justify-end");
      expect(within(item as HTMLElement).getByText(detail)).toBeInTheDocument();
      expect(within(item as HTMLElement).getByText(number)).toHaveClass("bg-claret", "font-bold");
    }

    expect(screen.getAllByText("›")[0]).toHaveClass("text-rule");
    expect(screen.getAllByText("›")[0]).not.toHaveClass("opacity-30");
  });
});
