import { render, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { SteppedRibbon } from "@/components/hero/SteppedRibbon";

describe("SteppedRibbon", () => {
  test("renders the three labelled steps with claret numbered prefixes", () => {
    render(<SteppedRibbon />);

    const list = screen.getByRole("list");

    for (const [number, label] of [
      ["1", "Choose collection"],
      ["2", "Ask a topic"],
      ["3", "Get answers"],
    ] as const) {
      const item = within(list).getByText(label).closest("li");

      expect(item).toBeInTheDocument();
      expect(within(item as HTMLElement).getByText(number)).toHaveClass("text-claret", "font-bold");
    }
  });
});
