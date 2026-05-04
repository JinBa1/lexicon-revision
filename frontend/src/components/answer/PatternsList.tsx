import { CitationChip } from "@/components/shared/CitationChip";
import type { StudyPattern } from "@/lib/api/types";

export function PatternsList({
  patterns,
  chunkIdToPosition,
  onCitationActivate,
}: {
  patterns: StudyPattern[];
  chunkIdToPosition: Map<string, number>;
  onCitationActivate: (chunkId: string) => void;
}) {
  if (patterns.length === 0) return null;
  return (
    <section className="mt-12 border-t border-rule-soft pt-8">
      <div className="font-ui text-[10px] font-bold uppercase tracking-[0.2em] text-ink-muted">
        Patterns
      </div>
      <div className="mt-5 space-y-8">
        {patterns.map((pattern, i) => (
          <article key={`${pattern.label}-${i}`}>
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="font-ui text-[14px] font-extrabold text-claret">{i + 1}.</span>
              <h3 className="font-display text-[18px] font-bold leading-snug text-ink">
                {pattern.label}
              </h3>
              {pattern.supporting_chunk_ids.map((chunkId, j) => {
                const pos = chunkIdToPosition.get(chunkId);
                if (pos === undefined) return null;
                return (
                  <CitationChip
                    key={`${chunkId}-${j}`}
                    label={String(pos)}
                    targetChunkId={chunkId}
                    onActivate={onCitationActivate}
                  />
                );
              })}
            </div>
            <p className="mt-2 font-body text-[16px] leading-[1.6] text-ink-muted">
              {pattern.summary}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
