import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import { ActionPair } from "@/components/hero/ActionPair";

describe("ActionPair", () => {
  test("renders the answer and question actions", () => {
    render(<ActionPair onFindQuestions={() => {}} onGetAnswer={() => {}} />);

    expect(screen.getByRole("button", { name: "Get answer with sources" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Find questions" })).toBeInTheDocument();
  });

  test("calls the matching action callbacks", async () => {
    const onFindQuestions = vi.fn();
    const onGetAnswer = vi.fn();

    render(<ActionPair onFindQuestions={onFindQuestions} onGetAnswer={onGetAnswer} />);

    await userEvent.click(screen.getByRole("button", { name: "Get answer with sources" }));
    await userEvent.click(screen.getByRole("button", { name: "Find questions" }));

    expect(onGetAnswer).toHaveBeenCalledOnce();
    expect(onFindQuestions).toHaveBeenCalledOnce();
  });
});
