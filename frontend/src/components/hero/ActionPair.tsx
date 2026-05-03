import { Button } from "@/components/shared/Button";
import { cn } from "@/lib/cn";

export function ActionPair({
  onFindQuestions,
  onGetAnswer,
  chrome = "default",
}: {
  onFindQuestions: () => void;
  onGetAnswer: () => void;
  chrome?: "default" | "landing-unified" | "result-unified";
}) {
  if (chrome === "landing-unified" || chrome === "result-unified") {
    const isResultUnified = chrome === "result-unified";

    return (
      <div className="inline-flex flex-col gap-3 sm:flex-row sm:justify-end">
        <Button
          variant="primary"
          onClick={onGetAnswer}
          className={cn(
            "min-h-14 justify-center px-7 font-display normal-case tracking-normal",
            isResultUnified
              ? "text-[16px] shadow-[0_2px_8px_rgba(126,46,46,0.18)]"
              : "text-[17px] shadow-[0_6px_16px_rgba(126,46,46,0.16)]",
          )}
        >
          <span aria-hidden>📄</span>
          Get answer with sources
        </Button>
        <Button
          variant="secondary"
          onClick={onFindQuestions}
          className={cn(
            "min-h-14 justify-center bg-white px-7 font-display font-semibold normal-case tracking-normal",
            isResultUnified ? "text-[16px]" : "text-[17px]",
          )}
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
