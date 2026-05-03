import { Button } from "@/components/shared/Button";

export function ActionPair({
  onFindQuestions,
  onGetAnswer,
  chrome = "default",
}: {
  onFindQuestions: () => void;
  onGetAnswer: () => void;
  chrome?: "default" | "landing-unified";
}) {
  if (chrome === "landing-unified") {
    return (
      <div className="inline-flex flex-col gap-3 sm:flex-row sm:justify-end">
        <Button
          variant="primary"
          onClick={onGetAnswer}
          className="min-h-14 justify-center px-7 font-display text-[17px] normal-case tracking-normal shadow-[0_6px_16px_rgba(126,46,46,0.16)]"
        >
          <span aria-hidden>📄</span>
          Get answer with sources
        </Button>
        <Button
          variant="secondary"
          onClick={onFindQuestions}
          className="min-h-14 justify-center bg-white px-7 font-display text-[17px] font-semibold normal-case tracking-normal"
        >
          <span aria-hidden>🔍</span>
          Find questions
        </Button>
      </div>
    );
  }

  return (
    <div className="flex gap-2">
      <Button variant="secondary" onClick={onGetAnswer} className="text-xs">
        Get answer with sources
      </Button>
      <Button variant="primary" onClick={onFindQuestions} className="text-xs">
        Find questions
      </Button>
    </div>
  );
}
