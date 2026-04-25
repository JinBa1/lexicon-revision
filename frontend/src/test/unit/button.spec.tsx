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

  test("applies primary variant classes", () => {
    render(<Button variant="primary">X</Button>);
    const btn = screen.getByRole("button");
    expect(btn.className).toContain("bg-claret");
  });

  test("applies secondary variant classes", () => {
    render(<Button variant="secondary">X</Button>);
    const btn = screen.getByRole("button");
    expect(btn.className).toContain("text-claret");
  });

  test("forwards type attribute", () => {
    render(<Button type="submit">Go</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "submit");
  });
});
