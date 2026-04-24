import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { FiltersPopover } from "@/components/filters/FiltersPopover";
import { FiltersChip } from "@/components/hero/FiltersChip";
import type { CollectionMetadataSchema, FilterCondition } from "@/lib/api/types";

const schema = {
  version: 1,
  fields: [
    {
      key: "year",
      label: "Year",
      type: "integer",
      operators: ["eq", "gte", "lte"],
      exposed: true,
      source: null,
    },
    {
      key: "difficulty",
      label: "Difficulty",
      type: "string",
      operators: ["eq"],
      exposed: true,
      source: null,
    },
    {
      key: "has_solution",
      label: "Has solution",
      type: "boolean",
      operators: ["eq"],
      exposed: true,
      source: null,
    },
    {
      key: "internal_code",
      label: "Internal code",
      type: "string",
      operators: ["eq"],
      exposed: false,
      source: null,
    },
  ],
} satisfies CollectionMetadataSchema;

const integerFallbackSchema = {
  version: 1,
  fields: [
    {
      key: "paper",
      label: "Paper",
      type: "integer",
      operators: ["eq"],
      exposed: true,
      source: null,
    },
  ],
} satisfies CollectionMetadataSchema;

describe("FiltersPopover", () => {
  test("renders an empty-state message when no schema fields are available", () => {
    render(<FiltersPopover schema={null} value={[]} onChange={() => {}} onClose={() => {}} />);

    expect(screen.getByText("No filters available for this collection.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Filters" })).not.toBeInTheDocument();
  });

  test("renders exposed schema fields with suitable controls", () => {
    render(<FiltersPopover schema={schema} value={[]} onChange={() => {}} onClose={() => {}} />);

    expect(screen.getByRole("dialog", { name: "Filters" })).toBeInTheDocument();
    expect(screen.getByText("Year")).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: "Year from" })).toHaveAttribute(
      "placeholder",
      "From",
    );
    expect(screen.getByRole("spinbutton", { name: "Year to" })).toHaveAttribute(
      "placeholder",
      "To",
    );
    expect(screen.getByRole("textbox", { name: "Difficulty" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Has solution" })).toBeInTheDocument();
    expect(screen.queryByText("Internal code")).not.toBeInTheDocument();
  });

  test("updates number range, boolean, and text filters as ordered filter conditions", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    let value: FilterCondition[] = [];

    const { rerender } = render(
      <FiltersPopover schema={schema} value={value} onChange={onChange} onClose={() => {}} />,
    );

    fireEvent.change(screen.getByRole("spinbutton", { name: "Year from" }), {
      target: { value: "2020" },
    });
    expect(onChange).toHaveBeenLastCalledWith([{ field: "year", op: "gte", value: 2020 }]);

    value = onChange.mock.lastCall?.[0] ?? [];
    rerender(
      <FiltersPopover schema={schema} value={value} onChange={onChange} onClose={() => {}} />,
    );

    await user.selectOptions(screen.getByRole("combobox", { name: "Has solution" }), "true");
    expect(onChange).toHaveBeenLastCalledWith([
      { field: "year", op: "gte", value: 2020 },
      { field: "has_solution", op: "eq", value: true },
    ]);

    value = onChange.mock.lastCall?.[0] ?? [];
    rerender(
      <FiltersPopover schema={schema} value={value} onChange={onChange} onClose={() => {}} />,
    );

    fireEvent.change(screen.getByRole("textbox", { name: "Difficulty" }), {
      target: { value: "hard" },
    });
    expect(onChange).toHaveBeenLastCalledWith([
      { field: "year", op: "gte", value: 2020 },
      { field: "has_solution", op: "eq", value: true },
      { field: "difficulty", op: "eq", value: "hard" },
    ]);
  });

  test("removes range conditions for invalid or fractional integer input", () => {
    const onChange = vi.fn();

    render(
      <FiltersPopover
        schema={schema}
        value={[
          { field: "year", op: "gte", value: 2020 },
          { field: "year", op: "lte", value: 2024 },
          { field: "difficulty", op: "eq", value: "hard" },
        ]}
        onChange={onChange}
        onClose={() => {}}
      />,
    );

    fireEvent.change(screen.getByRole("spinbutton", { name: "Year from" }), {
      target: { value: "1.5" },
    });
    expect(onChange).toHaveBeenLastCalledWith([
      { field: "year", op: "lte", value: 2024 },
      { field: "difficulty", op: "eq", value: "hard" },
    ]);

    fireEvent.change(screen.getByRole("spinbutton", { name: "Year to" }), {
      target: { value: "12abc" },
    });
    expect(onChange).toHaveBeenLastCalledWith([
      { field: "year", op: "gte", value: 2020 },
      { field: "difficulty", op: "eq", value: "hard" },
    ]);
  });

  test("keeps integer fallback text-field values numeric", () => {
    const onChange = vi.fn();

    render(
      <FiltersPopover
        schema={integerFallbackSchema}
        value={[]}
        onChange={onChange}
        onClose={() => {}}
      />,
    );

    fireEvent.change(screen.getByRole("spinbutton", { name: "Paper" }), {
      target: { value: "3" },
    });

    expect(onChange).toHaveBeenCalledWith([{ field: "paper", op: "eq", value: 3 }]);
  });

  test("removes integer fallback conditions for invalid or fractional input", () => {
    const onChange = vi.fn();

    const { rerender } = render(
      <FiltersPopover
        schema={integerFallbackSchema}
        value={[{ field: "paper", op: "eq", value: 3 }]}
        onChange={onChange}
        onClose={() => {}}
      />,
    );

    fireEvent.change(screen.getByRole("spinbutton", { name: "Paper" }), {
      target: { value: "1.5" },
    });
    expect(onChange).toHaveBeenLastCalledWith([]);

    rerender(
      <FiltersPopover
        schema={integerFallbackSchema}
        value={[{ field: "paper", op: "eq", value: 3 }]}
        onChange={onChange}
        onClose={() => {}}
      />,
    );

    fireEvent.change(screen.getByRole("spinbutton", { name: "Paper" }), {
      target: { value: "12abc" },
    });
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  test("clear all and done controls call their handlers", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onClose = vi.fn();

    render(
      <FiltersPopover
        schema={schema}
        value={[{ field: "difficulty", op: "eq", value: "hard" }]}
        onChange={onChange}
        onClose={onClose}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Clear all" }));
    expect(onChange).toHaveBeenCalledWith([]);

    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("FiltersChip", () => {
  test("opens, shows the active filter count, and closes when clicked again", async () => {
    const user = userEvent.setup();

    render(
      <FiltersChip
        schema={schema}
        value={[{ field: "difficulty", op: "eq", value: "hard" }]}
        onChange={() => {}}
      />,
    );

    const chip = screen.getByRole("button", { name: "+ Filters (1)" });

    await user.click(chip);
    expect(screen.getByRole("dialog", { name: "Filters" })).toBeInTheDocument();
    expect(chip).toHaveAttribute("aria-expanded", "true");

    await user.click(chip);
    expect(screen.queryByRole("dialog", { name: "Filters" })).not.toBeInTheDocument();
    expect(chip).toHaveAttribute("aria-expanded", "false");
  });

  test("closes the popover after an outside click", async () => {
    const user = userEvent.setup();

    render(
      <div>
        <FiltersChip schema={schema} value={[]} onChange={() => {}} />
        <button type="button">Outside</button>
      </div>,
    );

    await user.click(screen.getByRole("button", { name: "+ Filters" }));
    expect(screen.getByRole("dialog", { name: "Filters" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Outside" }));
    expect(screen.queryByRole("dialog", { name: "Filters" })).not.toBeInTheDocument();
  });
});
