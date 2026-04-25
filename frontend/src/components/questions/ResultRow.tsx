import { ChunkCard } from "@/components/shared/ChunkCard";
import type { SearchResult } from "@/lib/api/types";

export function ResultRow({
  result,
  selected,
  onSelect,
}: {
  result: SearchResult;
  selected: boolean;
  onSelect: (chunkId: string) => void;
}) {
  return (
    <ChunkCard
      mode="compact"
      chunk={{
        chunk_id: result.chunk_id,
        chunk_level: result.chunk_level,
        parent_chunk_id: result.parent_chunk_id,
        sub_question_label: result.sub_question_label,
        text: result.text,
        metadata: result.metadata,
        media: result.media,
      }}
      selected={selected}
      onClick={() => onSelect(result.chunk_id)}
    />
  );
}
