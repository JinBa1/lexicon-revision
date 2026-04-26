import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { Chip } from "@/components/shared/Chip";

describe("Chip", () => {
  test("renders as button when onClick provided", () => {
    const { container } = render(<Chip onClick={() => {}}>Cam</Chip>);
    expect(container.querySelector("button")).not.toBeNull();
  });

  test("renders as span when no handler", () => {
    const { container } = render(<Chip>Cam</Chip>);
    expect(container.querySelector("button")).toBeNull();
    expect(screen.getByText("Cam")).toBeInTheDocument();
  });

  test("ghost variant uses transparent background", () => {
    render(<Chip variant="ghost">X</Chip>);
    expect(screen.getByText("X").className).toContain("bg-transparent");
  });

  it("renders meta variant with low-emphasis classes", () => {
    const { container } = render(<Chip variant="meta">Year 2024</Chip>);
    const node = container.firstChild as HTMLElement;
    expect(node.className).toContain("border-rule-soft");
    expect(node.textContent).toBe("Year 2024");
  });
});
