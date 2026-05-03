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

  test("landing-unified chrome makes answer primary and question search secondary with icons", () => {
    render(
      <ActionPair chrome="landing-unified" onFindQuestions={() => {}} onGetAnswer={() => {}} />,
    );

    const answer = screen.getByRole("button", { name: "Get answer with sources" });
    const questions = screen.getByRole("button", { name: "Find questions" });
    const answerIcon = answer.querySelector('span[aria-hidden="true"]');
    const questionsIcon = questions.querySelector('span[aria-hidden="true"]');

    expect(answer).toHaveClass("bg-claret", "text-paper-raised");
    expect(questions).toHaveClass("bg-white", "text-claret");
    expect(answerIcon).toHaveTextContent("📄");
    expect(questionsIcon).toHaveTextContent("🔍");
  });

  test("result-unified chrome uses the compact mockup button scale", () => {
    render(
      <ActionPair chrome="result-unified" onFindQuestions={() => {}} onGetAnswer={() => {}} />,
    );

    const answer = screen.getByRole("button", { name: "Get answer with sources" });
    const questions = screen.getByRole("button", { name: "Find questions" });

    expect(answer).toHaveClass(
      "min-h-14",
      "text-[16px]",
      "shadow-[0_2px_8px_rgba(126,46,46,0.18)]",
    );
    expect(questions).toHaveClass("min-h-14", "text-[16px]", "bg-white");
  });
});
