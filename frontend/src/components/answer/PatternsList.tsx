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
    <div>
      <div className="my-3 flex items-center gap-3">
        <span className="font-ui text-[10px] uppercase tracking-[0.14em] text-ink-muted">
          Patterns
        </span>
        <span className="h-px flex-1 bg-rule" />
      </div>
      <ol className="list-decimal space-y-3 pl-5 font-body text-[14px] leading-relaxed">
        {patterns.map((pattern, i) => (
          <li key={`${pattern.label}-${i}`}>
            <span className="font-semibold">{pattern.label}</span>
            {pattern.supporting_chunk_ids.length > 0 ? (
              <span className="ml-1">
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
              </span>
            ) : null}
            <span className="mt-1 block text-ink-muted">{pattern.summary}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
