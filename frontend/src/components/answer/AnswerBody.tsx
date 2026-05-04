export function AnswerBody({ overview }: { overview: string }) {
  return (
    <section>
      <div className="font-ui text-[10px] font-bold uppercase tracking-[0.2em] text-ink-muted">
        The Answer
      </div>
      <p className="mt-4 max-w-[65ch] whitespace-pre-wrap font-body text-[17px] leading-[1.7] text-ink">
        {overview}
      </p>
    </section>
  );
}
