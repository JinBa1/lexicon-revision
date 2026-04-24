import { Button } from "@/components/shared/Button";

export function ActionPair({
  onFindQuestions,
  onGetAnswer,
}: {
  onFindQuestions: () => void;
  onGetAnswer: () => void;
}) {
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
