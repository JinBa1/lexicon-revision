import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { ScopeChip } from "@/components/hero/ScopeChip";
import type { CollectionListItem } from "@/lib/api/types";

const collection = {
  name: "cam-cs-tripos",
  display_name: "Cambridge CS Tripos",
  community: null,
  paper_count: 12,
  year_range: { start: 2020, end: 2024 },
  metadata_schema: null,
  access_state: "accessible",
  lock_reason: null,
} satisfies CollectionListItem;

describe("ScopeChip", () => {
  test("renders the unselected label without aria-expanded by default", () => {
    render(<ScopeChip collection={null} onOpen={() => {}} />);

    const button = screen.getByRole("button", { name: "Pick a collection ▾" });

    expect(button).toHaveAttribute("title", "Pick a collection");
    expect(button).toHaveAttribute("aria-haspopup");
    expect(button).not.toHaveAttribute("aria-expanded");
  });

  test("renders the selected collection label", () => {
    render(<ScopeChip collection={collection} onOpen={() => {}} />);

    const button = screen.getByRole("button", { name: "Cambridge CS Tripos ▾" });

    expect(button).toHaveAttribute("title", "Cambridge CS Tripos");
  });

  test("calls onOpen when activated", async () => {
    const onOpen = vi.fn();
    render(<ScopeChip collection={collection} onOpen={onOpen} />);

    await userEvent.click(screen.getByRole("button", { name: "Cambridge CS Tripos ▾" }));

    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  test("passes aria-expanded only when open state is provided", () => {
    const { rerender } = render(<ScopeChip collection={null} onOpen={() => {}} open={false} />);

    expect(screen.getByRole("button", { name: "Pick a collection ▾" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    rerender(<ScopeChip collection={null} onOpen={() => {}} open />);

    expect(screen.getByRole("button", { name: "Pick a collection ▾" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
