import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

describe("smoke", () => {
  test("renders basic text", () => {
    render(<p>hello</p>);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });
});
