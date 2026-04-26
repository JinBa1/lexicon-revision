import { ChunkCard } from "@/components/shared/ChunkCard";
import type { CollectionMetadataSchema, SearchResult } from "@/lib/api/types";

export function ResultRow({
  result,
  selected,
  onSelect,
  metadataSchema,
}: {
  result: SearchResult;
  selected: boolean;
  onSelect: (chunkId: string) => void;
  metadataSchema: CollectionMetadataSchema | null;
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
        render_blocks: result.render_blocks,
      }}
      metadataSchema={metadataSchema}
      selected={selected}
      onClick={() => onSelect(result.chunk_id)}
    />
  );
}
