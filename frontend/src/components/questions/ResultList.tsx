import type { SearchResult } from "@/lib/api/types";
import { ResultRow } from "./ResultRow";

export function ResultList({
  results,
  total,
  selectedChunkId,
  onSelect,
}: {
  results: SearchResult[];
  total: number;
  selectedChunkId: string | null;
  onSelect: (chunkId: string) => void;
}) {
  return (
    <div className="border-r border-rule">
      <div className="px-4 py-3 font-display text-[11px] uppercase tracking-widest text-ink-muted">
        {total} {total === 1 ? "question matches" : "questions match"}
      </div>
      <ul className="divide-y divide-rule/50">
        {results.map((result) => (
          <li key={result.chunk_id} className="px-1.5">
            <ResultRow
              result={result}
              selected={selectedChunkId === result.chunk_id}
              onSelect={onSelect}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
