const STEPS = ["Choose collection", "Ask a topic", "Get answers"] as const;

export function SteppedRibbon() {
  return (
    <ol className="mb-4 flex flex-wrap justify-center gap-x-6 gap-y-1 text-[12px] text-ink-muted">
      {STEPS.map((label, index) => (
        <li key={label} className="font-ui">
          <span className="font-bold text-claret">{index + 1}</span> <span>{label}</span>
        </li>
      ))}
    </ol>
  );
}
