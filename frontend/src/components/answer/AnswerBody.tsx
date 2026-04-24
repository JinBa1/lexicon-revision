export function AnswerBody({ overview }: { overview: string }) {
  return (
    <div>
      <SectionHeader>Answer</SectionHeader>
      <p className="max-w-[65ch] whitespace-pre-wrap font-body text-[15px] leading-relaxed text-ink">
        {overview}
      </p>
    </div>
  );
}

function SectionHeader({ children }: { children: string }) {
  return (
    <div className="my-3 flex items-center gap-3">
      <span className="font-ui text-[10px] uppercase tracking-[0.14em] text-ink-muted">
        {children}
      </span>
      <span className="h-px flex-1 bg-rule" />
    </div>
  );
}
