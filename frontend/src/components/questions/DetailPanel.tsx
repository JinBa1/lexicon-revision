import { ChunkCard } from "@/components/shared/ChunkCard";
import { LoadingSkeleton } from "@/components/shared/LoadingSkeleton";
import { EmptyState } from "@/components/shared/EmptyState";
import { buildSourceHref } from "@/lib/url/scope";
import { Link, useLocation } from "react-router-dom";
import type { ChunkDetail, CollectionMetadataSchema } from "@/lib/api/types";

export function DetailPanel({
  collection,
  chunk,
  isLoading,
  metadataSchema,
}: {
  collection: string;
  chunk: ChunkDetail | undefined;
  isLoading: boolean;
  metadataSchema?: CollectionMetadataSchema | null;
}) {
  const location = useLocation();
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
        metadataSchema={metadataSchema}
        footer={
          <Link
            to={buildSourceHref(collection, chunk.chunk_id)}
            state={{ from: location.pathname + location.search }}
            className="inline-flex items-center justify-center rounded-sm bg-claret px-4 py-2 font-ui text-[12px] font-medium text-paper-raised transition-colors hover:bg-claret/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 focus-visible:ring-offset-paper-raised"
          >
            Open shareable source →
          </Link>
        }
      />
    </div>
  );
}
