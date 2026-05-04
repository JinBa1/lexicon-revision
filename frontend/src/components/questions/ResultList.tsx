import type { CollectionMetadataSchema, SearchResult } from "@/lib/api/types";
import { ResultRow } from "./ResultRow";

export function ResultList({
  results,
  total,
  selectedChunkId,
  onSelect,
  metadataSchema,
}: {
  results: SearchResult[];
  total?: number;
  selectedChunkId: string | null;
  onSelect: (chunkId: string) => void;
  metadataSchema: CollectionMetadataSchema | null;
}) {
  const count = total ?? results.length;
  const noun = count === 1 ? "question" : "questions";

  return (
    <section className="flex min-w-0 flex-col gap-3">
      <div className="mb-1">
        <h2 className="font-display text-[22px] font-bold text-ink">
          {count} matching {noun}
        </h2>
        <p className="mt-1 font-ui text-[12px] tracking-[0.04em] text-ink-muted">
          Ranked by relevance to your query
        </p>
      </div>
      <ul className="flex flex-col gap-3">
        {results.map((result, index) => (
          <li key={result.chunk_id}>
            <ResultRow
              rank={index + 1}
              result={result}
              selected={selectedChunkId === result.chunk_id}
              onSelect={onSelect}
              metadataSchema={metadataSchema}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
