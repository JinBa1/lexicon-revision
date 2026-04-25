export type HelperExampleAction = "questions" | "answer";

export type HelperExample = {
  label: string;
  action: HelperExampleAction;
};

const DEFAULT_EXAMPLES: HelperExample[] = [
  { label: "binary search", action: "questions" },
  { label: "amortized analysis", action: "questions" },
  { label: "graph flows", action: "questions" },
  { label: "How do past papers examine amortized analysis?", action: "answer" },
  { label: "Explain graph flows using past-paper examples.", action: "answer" },
];

export function HelperExamples({
  examples = DEFAULT_EXAMPLES,
  onPick,
}: {
  examples?: HelperExample[];
  onPick: (example: HelperExample) => void;
}) {
  const findExamples = examples.filter((e) => e.action === "questions");
  const answerExamples = examples.filter((e) => e.action === "answer");
  return (
    <div className="mt-3 space-y-2 border-t border-rule-soft pt-3 font-body text-sm text-ink-muted">
      {findExamples.length > 0 ? <Row label="Try" items={findExamples} onPick={onPick} /> : null}
      {answerExamples.length > 0 ? (
        <Row label="Or ask" items={answerExamples} onPick={onPick} />
      ) : null}
    </div>
  );
}

function Row({
  label,
  items,
  onPick,
}: {
  label: string;
  items: HelperExample[];
  onPick: (example: HelperExample) => void;
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span className="font-ui text-[10px] uppercase tracking-wider text-claret">{label}</span>
      {items.map((example, idx) => (
        <span key={`${example.label}-${idx}`}>
          <button
            type="button"
            onClick={() => onPick(example)}
            className="cursor-pointer italic text-ink underline decoration-rule-soft underline-offset-[3px] hover:decoration-claret"
          >
            {example.label}
          </button>
          {idx < items.length - 1 ? <span> · </span> : null}
        </span>
      ))}
    </div>
  );
}
