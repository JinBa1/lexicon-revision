import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { Hero } from "@/components/hero/Hero";
import type { CollectionListItem } from "@/lib/api/types";

const accessible: CollectionListItem = {
  name: "cam-cs-tripos",
  display_name: "Cambridge CS Tripos",
  community: { id: "c-cam", display_name: "Cambridge" },
  paper_count: 744,
  year_range: { start: 2018, end: 2025 },
  metadata_schema: {
    version: 1,
    fields: [
      {
        key: "year",
        label: "Year",
        type: "integer",
        operators: ["gte", "lte"],
        exposed: true,
        source: null,
      },
    ],
  },
  access_state: "accessible",
  lock_reason: null,
};

function wrap(ui: React.ReactNode) {
  return <MemoryRouter>{ui}</MemoryRouter>;
}

describe("Hero", () => {
  test("renders persistent helper when no scope is set", () => {
    render(
      wrap(
        <Hero
          mode="landing"
          activeCollection={null}
          query=""
          filters={[]}
          onQueryChange={() => {}}
          onFiltersChange={() => {}}
          onOpenScope={() => {}}
          onSubmit={() => {}}
        />,
      ),
    );
    expect(screen.getByText(/Pick a collection below to enable search/i)).toBeInTheDocument();
  });

  test("replaces helper with meta line when scope is set", () => {
    render(
      wrap(
        <Hero
          mode="landing"
          activeCollection={accessible}
          query=""
          filters={[]}
          onQueryChange={() => {}}
          onFiltersChange={() => {}}
          onOpenScope={() => {}}
          onSubmit={() => {}}
        />,
      ),
    );
    expect(screen.getByText(/744 papers/)).toBeInTheDocument();
    expect(screen.queryByText(/Pick a collection/i)).toBeNull();
  });

  test("intercepts submit when scope null and calls onScopeMissing", async () => {
    const onSubmit = vi.fn();
    const onScopeMissing = vi.fn();
    render(
      wrap(
        <Hero
          mode="landing"
          activeCollection={null}
          query="topic"
          filters={[]}
          onQueryChange={() => {}}
          onFiltersChange={() => {}}
          onOpenScope={() => {}}
          onSubmit={onSubmit}
          onScopeMissing={onScopeMissing}
        />,
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: /Find questions/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(onScopeMissing).toHaveBeenCalledOnce();
  });

  test("submits Find questions when scope is set", async () => {
    const onSubmit = vi.fn();
    render(
      wrap(
        <Hero
          mode="landing"
          activeCollection={accessible}
          query="topic"
          filters={[]}
          onQueryChange={() => {}}
          onFiltersChange={() => {}}
          onOpenScope={() => {}}
          onSubmit={onSubmit}
        />,
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: /Find questions/i }));
    expect(onSubmit).toHaveBeenCalledWith("questions");
  });

  test("Enter in the query input fires primary action", async () => {
    const onSubmit = vi.fn();
    render(
      wrap(
        <Hero
          mode="landing"
          activeCollection={accessible}
          query=""
          filters={[]}
          onQueryChange={() => {}}
          onFiltersChange={() => {}}
          onOpenScope={() => {}}
          onSubmit={onSubmit}
        />,
      ),
    );
    const input = screen.getByLabelText(/query/i);
    await userEvent.type(input, "amortized{Enter}");
    expect(onSubmit).toHaveBeenCalledWith("questions");
  });

  test("helper example click fills input and fires matching action", async () => {
    const onQueryChange = vi.fn();
    const onSubmit = vi.fn();
    render(
      wrap(
        <Hero
          mode="landing"
          activeCollection={accessible}
          query=""
          filters={[]}
          onQueryChange={onQueryChange}
          onFiltersChange={() => {}}
          onOpenScope={() => {}}
          onSubmit={onSubmit}
        />,
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: /binary search/i }));
    expect(onQueryChange).toHaveBeenCalledWith("binary search");
    expect(onSubmit).toHaveBeenCalledWith("questions");
  });

  test("header-echo mode hides helper examples", () => {
    render(
      wrap(
        <Hero
          mode="header-echo"
          activeCollection={accessible}
          query="x"
          filters={[]}
          onQueryChange={() => {}}
          onFiltersChange={() => {}}
          onOpenScope={() => {}}
          onSubmit={() => {}}
        />,
      ),
    );
    expect(screen.queryByText(/Try/)).toBeNull();
  });
});
