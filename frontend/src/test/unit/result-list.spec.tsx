import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { ResultList } from "@/components/questions/ResultList";
import { questionResult, subQuestionResult } from "../fixtures/search";

describe("ResultList", () => {
  test("renders singular match count", () => {
    render(
      <ResultList
        results={[questionResult]}
        total={1}
        selectedChunkId={null}
        onSelect={() => {}}
      />,
    );

    expect(screen.getByText("1 question matches")).toBeInTheDocument();
  });

  test("renders plural match count", () => {
    render(
      <ResultList
        results={[questionResult, subQuestionResult]}
        total={2}
        selectedChunkId={null}
        onSelect={() => {}}
      />,
    );

    expect(screen.getByText("2 questions match")).toBeInTheDocument();
  });

  test("marks the selected row and selects rows by chunk id", async () => {
    const onSelect = vi.fn();

    render(
      <ResultList
        results={[questionResult, subQuestionResult]}
        total={2}
        selectedChunkId={subQuestionResult.chunk_id}
        onSelect={onSelect}
      />,
    );

    expect(screen.getByRole("button", { name: /halves on underflow/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /amortized analysis/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    await userEvent.click(screen.getByRole("button", { name: /amortized analysis/i }));

    expect(onSelect).toHaveBeenCalledWith(questionResult.chunk_id);
  });
});
