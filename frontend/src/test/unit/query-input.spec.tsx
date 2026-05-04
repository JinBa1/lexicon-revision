import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { QueryInput } from "@/components/hero/QueryInput";

describe("QueryInput", () => {
  test("renders the default accessible query field", () => {
    render(<QueryInput />);

    const input = screen.getByRole("textbox", { name: "Query" });

    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("placeholder", "Enter a topic or a question…");
  });

  test("supports typing", async () => {
    render(<QueryInput size="md" />);

    const input = screen.getByRole("textbox", { name: "Query" });

    await userEvent.type(input, "binary search trees");
    expect(input).toHaveValue("binary search trees");
  });

  test("forwards input props", async () => {
    const onChange = vi.fn();
    render(<QueryInput name="query" autoComplete="off" onChange={onChange} />);

    const input = screen.getByRole("textbox", { name: "Query" });

    expect(input).toHaveAttribute("name", "query");
    expect(input).toHaveAttribute("autocomplete", "off");
    await userEvent.type(input, "x");
    expect(onChange).toHaveBeenCalled();
  });

  test("forwards refs to the input element", () => {
    const ref = createRef<HTMLInputElement>();

    render(<QueryInput ref={ref} />);

    expect(ref.current).toBe(screen.getByRole("textbox", { name: "Query" }));
  });
});
