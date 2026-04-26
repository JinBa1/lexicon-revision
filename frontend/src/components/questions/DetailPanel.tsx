import { ChunkCard } from "@/components/shared/ChunkCard";
import { LoadingSkeleton } from "@/components/shared/LoadingSkeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { buildSourceHref } from "@/lib/url/scope";
import { Link } from "react-router-dom";
import type { ChunkDetail } from "@/lib/api/types";

export function DetailPanel({
  collection,
  chunk,
  isLoading,
}: {
  collection: string;
  chunk: ChunkDetail | undefined;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className="p-6">
        <LoadingSkeleton variant="prose" count={8} />
      </div>
    );
  }
  if (!chunk) {
    return (
      <EmptyState
        title="Select a result"
        detail="Pick a question on the left to see full text, metadata, and media."
      />
    );
  }
  return (
    <div className="p-6">
      <ChunkCard
        mode="full"
        chunk={{
          chunk_id: chunk.chunk_id,
          chunk_level: chunk.chunk_level,
          parent_chunk_id: chunk.parent_chunk_id,
          sub_question_label: chunk.sub_question_label,
          text: chunk.text,
          metadata: chunk.metadata,
          media: chunk.media,
          render_blocks: chunk.render_blocks,
        }}
        parent={
          chunk.parent
            ? {
                text: chunk.parent.text,
                metadata: chunk.parent.metadata,
                render_blocks: chunk.parent.render_blocks,
              }
            : null
        }
        footer={
          <Link
            to={buildSourceHref(collection, chunk.chunk_id)}
            className="font-ui text-[11px] uppercase tracking-widest text-claret hover:underline"
          >
            Open as shareable source →
          </Link>
        }
      />
    </div>
  );
}
