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
  total: number;
  selectedChunkId: string | null;
  onSelect: (chunkId: string) => void;
  metadataSchema: CollectionMetadataSchema | null;
}) {
  void total;
  return (
    <div className="border-r border-rule">
      <h2 className="px-4 py-3 font-display text-lg text-ink">Top {results.length} results</h2>
      <ul className="divide-y divide-rule/50">
        {results.map((result) => (
          <li key={result.chunk_id} className="px-1.5">
            <ResultRow
              result={result}
              selected={selectedChunkId === result.chunk_id}
              onSelect={onSelect}
              metadataSchema={metadataSchema}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
