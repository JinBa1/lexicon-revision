export function LimitationsBlock({ limitations }: { limitations: string[] }) {
  if (limitations.length === 0) return null;

  return (
    <aside
      aria-labelledby="limitations-heading"
      className="my-4 border-l-4 border-claret bg-claret-soft py-3 pl-4 pr-3 font-body text-[13px] leading-relaxed"
    >
      <div id="limitations-heading" className="section-eyebrow">
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
