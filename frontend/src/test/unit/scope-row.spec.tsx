import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { ScopeRow } from "@/components/hero/ScopeRow";
import type { CollectionListItem, FilterCondition } from "@/lib/api/types";

const collection = {
  name: "cam-cs-tripos",
  display_name: "Cambridge CS Tripos",
  community: null,
  paper_count: 12,
  year_range: { start: 2020, end: 2024 },
  metadata_schema: {
    version: 1,
    fields: [
      {
        key: "year",
        label: "Year",
        type: "integer",
        operators: ["eq", "gte", "lte"],
        exposed: true,
        source: "paper",
      },
    ],
  },
  access_state: "accessible",
  lock_reason: null,
} satisfies CollectionListItem;

const filters = [{ field: "year", op: "gte", value: 2020 }] satisfies FilterCondition[];

describe("ScopeRow", () => {
  test("renders the scope label, active collection, filters, and actions", () => {
    render(
      <ScopeRow
        activeCollection={collection}
        filters={filters}
        onFiltersChange={() => {}}
        onOpenScope={() => {}}
        onSubmit={() => {}}
      />,
    );

    expect(screen.getByText("In")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cambridge CS Tripos ▾" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+ Filters (1)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Get answer with sources" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Find questions" })).toBeInTheDocument();
  });

  test("routes action clicks and scope opening to callbacks", async () => {
    const onOpenScope = vi.fn();
    const onSubmit = vi.fn();

    render(
      <ScopeRow
        activeCollection={collection}
        filters={[]}
        onFiltersChange={() => {}}
        onOpenScope={onOpenScope}
        onSubmit={onSubmit}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Cambridge CS Tripos ▾" }));
    await userEvent.click(screen.getByRole("button", { name: "Find questions" }));
    await userEvent.click(screen.getByRole("button", { name: "Get answer with sources" }));

    expect(onOpenScope).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenNthCalledWith(1, "questions");
    expect(onSubmit).toHaveBeenNthCalledWith(2, "answer");
  });
});
