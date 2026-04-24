export function LimitationsBlock({ limitations }: { limitations: string[] }) {
  if (limitations.length === 0) return null;
  return (
    <div className="mt-4 rounded-sm border border-rule bg-paper-raised px-4 py-3 font-body text-[13px] leading-relaxed">
      <div className="mb-1 font-ui text-[10px] uppercase tracking-[0.14em] text-ink-muted">
        Limitations
      </div>
      <ul className="list-disc space-y-1 pl-5">
        {limitations.map((limitation, i) => (
          <li key={i}>{limitation}</li>
        ))}
      </ul>
    </div>
  );
}
