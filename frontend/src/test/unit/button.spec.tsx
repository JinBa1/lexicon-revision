import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import { Button } from "@/components/shared/Button";

describe("Button", () => {
  test("renders children", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: "Click me" })).toBeInTheDocument();
  });

  test("calls onClick", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  test("accepts primary variant", () => {
    render(<Button variant="primary">X</Button>);
    expect(screen.getByRole("button", { name: "X" })).toBeInTheDocument();
  });

  test("accepts secondary variant", () => {
    render(<Button variant="secondary">X</Button>);
    expect(screen.getByRole("button", { name: "X" })).toBeInTheDocument();
  });

  test("forwards type attribute", () => {
    render(<Button type="submit">Go</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "submit");
  });
});
