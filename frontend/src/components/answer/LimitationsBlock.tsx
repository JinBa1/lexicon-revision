export function LimitationsBlock({ limitations }: { limitations: string[] }) {
  if (limitations.length === 0) return null;

  return (
    <aside
      aria-labelledby="limitations-heading"
      className="my-10 rounded-r-[4px] border-l-4 border-claret bg-claret-soft px-6 py-5 font-body text-[15px] leading-[1.6] text-ink"
    >
      <div
        id="limitations-heading"
        className="font-ui text-[11px] font-bold uppercase tracking-[0.15em] text-claret"
      >
        Limitations
      </div>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {limitations.map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ul>
    </aside>
  );
}
