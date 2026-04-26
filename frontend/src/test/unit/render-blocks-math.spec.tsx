import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Math } from "@/components/shared/render-blocks/Math";

describe("<Math>", () => {
  it("renders inline math via KaTeX", () => {
    const { container } = render(<Math latex="x^2" displayMode={false} />);

    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("renders display math when displayMode is true", () => {
    const { container } = render(<Math latex="\\int x dx" displayMode />);

    expect(container.querySelector(".katex-display")).not.toBeNull();
  });

  it("does not throw on invalid latex", () => {
    expect(() => render(<Math latex="\\unknownmacro{x}" displayMode={false} />)).not.toThrow();
  });
});
