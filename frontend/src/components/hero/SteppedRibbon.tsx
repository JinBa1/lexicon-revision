const STEPS = [
  {
    title: "Choose collection",
    detail: "Select the archive to search",
  },
  {
    title: "Ask a topic or question",
    detail: "Enter what you want to learn",
  },
  {
    title: "Get results",
    detail: "Choose your next step",
  },
] as const;

export function SteppedRibbon() {
  return (
    <ol className="flex flex-col gap-3 border-b border-rule-soft bg-[#FBFAF7] px-5 py-4 font-ui sm:px-9 md:flex-row md:items-center md:justify-between md:gap-5">
      {STEPS.map((step, index) => (
        <li key={step.title} className="flex min-w-0 flex-1 items-center justify-start gap-3">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-claret font-ui text-xs font-bold text-paper-raised">
            {index + 1}
          </span>
          <span className="min-w-0">
            <span className="block font-ui text-[13px] font-semibold leading-tight text-ink">
              {step.title}
            </span>
            <span className="block text-[11px] leading-tight text-ink-muted">{step.detail}</span>
          </span>
          {index < STEPS.length - 1 ? (
            <span aria-hidden className="ml-auto hidden text-2xl font-light text-rule md:block">
              ›
            </span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
