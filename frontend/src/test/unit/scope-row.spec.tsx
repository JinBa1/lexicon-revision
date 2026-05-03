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
  test("hides filter controls until a collection is selected", () => {
    render(
      <ScopeRow
        activeCollection={null}
        filters={[]}
        onFiltersChange={() => {}}
        onOpenScope={() => {}}
        onSubmit={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Pick a collection ▾" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /\+ Filters/ })).not.toBeInTheDocument();
  });

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

  test("landing-unified chrome renders a full-height picker box without filters when no collection is selected", () => {
    render(
      <ScopeRow
        chrome="landing-unified"
        activeCollection={null}
        filters={[]}
        onFiltersChange={() => {}}
        onOpenScope={() => {}}
        onSubmit={() => {}}
      />,
    );

    const picker = screen.getByRole("button", { name: "Pick a collection" });
    expect(picker).toHaveTextContent("Pick a collection");
    expect(picker).not.toHaveTextContent("▾");
    expect(picker).toHaveClass("min-h-14", "border-rule", "bg-[#FDFBF5]");
    expect(screen.getByTestId("hero-action-row")).toHaveClass("justify-between");
    expect(screen.getByTestId("hero-action-row").className).not.toMatch(/grid-cols/);
    expect(screen.getByText("Current Collection")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Filters" })).toBeNull();
  });

  test("landing-unified chrome renders scope and filters as peer boxes when selected", () => {
    render(
      <ScopeRow
        chrome="landing-unified"
        activeCollection={collection}
        filters={filters}
        onFiltersChange={() => {}}
        onOpenScope={() => {}}
        onSubmit={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: "Cambridge CS Tripos" })).toHaveClass("min-h-14");
    expect(screen.getByRole("button", { name: "Cambridge CS Tripos" })).not.toHaveTextContent("▾");
    const filtersButton = screen.getByRole("button", { name: "Filters (1)" });
    expect(filtersButton).toHaveClass("min-h-14", "h-full");
    expect(filtersButton.parentElement).toHaveClass("self-stretch");
  });
});
