import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test } from "vitest";

import { DetailPanel } from "@/components/questions/DetailPanel";
import { chunkDetailFixture } from "../fixtures/search";

function renderDetailPanel(props: React.ComponentProps<typeof DetailPanel>) {
  return render(
    <MemoryRouter>
      <DetailPanel {...props} />
    </MemoryRouter>,
  );
}

describe("DetailPanel", () => {
  test("renders a prose loading skeleton while detail is loading", () => {
    const { container } = renderDetailPanel({
      collection: "cam-cs-tripos",
      chunk: undefined,
      isLoading: true,
    });

    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(8);
    expect(screen.queryByText("Select a result")).not.toBeInTheDocument();
  });

  test("renders an empty prompt before a result is selected", () => {
    renderDetailPanel({
      collection: "cam-cs-tripos",
      chunk: undefined,
      isLoading: false,
    });

    expect(screen.getByText("Select a result")).toBeInTheDocument();
    expect(
      screen.getByText("Pick a question on the left to see full text, metadata, and media."),
    ).toBeInTheDocument();
  });

  test("renders full chunk detail with parent context and source link", () => {
    renderDetailPanel({
      collection: "cam-cs-tripos",
      chunk: chunkDetailFixture,
      isLoading: false,
    });

    expect(screen.getByText(/Give an amortized analysis/i)).toBeInTheDocument();
    expect(screen.getByText(/halves on underflow/i)).toBeInTheDocument();

    expect(screen.getByRole("link", { name: /open as shareable source/i })).toHaveAttribute(
      "href",
      "/c/cam-cs-tripos/source/cam-2022-p5-q3-b",
    );
  });
});
