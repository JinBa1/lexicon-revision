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

  test("accepts ghost variant", () => {
    render(<Chip variant="ghost">X</Chip>);
    expect(screen.getByText("X")).toBeInTheDocument();
  });

  it("accepts meta variant", () => {
    render(<Chip variant="meta">Year 2024</Chip>);
    expect(screen.getByText("Year 2024")).toBeInTheDocument();
  });
});
