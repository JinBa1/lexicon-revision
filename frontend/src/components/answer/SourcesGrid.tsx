import { Link } from "react-router-dom";
import { RenderBlocks } from "@/components/shared/render-blocks";
import type { CollectionMetadataSchema, StudySource } from "@/lib/api/types";
import { renderMetadataSummary } from "@/lib/metadata/render";
import { buildSourceHref } from "@/lib/url/scope";

export function SourcesGrid({
  collection,
  sources,
  highlightedChunkId,
  metadataSchema,
  registerRef,
}: {
  collection: string;
  sources: StudySource[];
  highlightedChunkId: string | null;
  metadataSchema?: CollectionMetadataSchema | null;
  registerRef: (chunkId: string, el: HTMLElement | null) => void;
}) {
  if (sources.length === 0) return null;
  return (
    <div className="mt-6">
      <div className="my-3 flex items-center gap-3">
        <span className="font-ui text-[10px] uppercase tracking-[0.14em] text-ink-muted">
          Sources
        </span>
        <span className="h-px flex-1 bg-rule" />
      </div>
      <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sources.map((source, i) => (
          <li
            key={source.chunk_id}
            ref={(el) => registerRef(source.chunk_id, el)}
            className={`rounded-sm border p-3 ${
              highlightedChunkId === source.chunk_id
                ? "border-claret bg-claret-soft"
                : "border-rule bg-paper-raised"
            }`}
          >
            <div
              className="font-display text-[10px] uppercase tracking-wide text-ink-muted"
              style={{ fontVariant: "small-caps" }}
            >
              {i + 1} · {renderMeta(source, metadataSchema)}
            </div>
            <RenderBlocks
              blocks={source.excerpt_blocks}
              mode="compact"
              fallbackText={source.excerpt}
              compactLines={4}
              className="mt-1"
            />
            {source.why_cited ? (
              <p className="mt-2 border-t border-dashed border-rule-soft pt-2 font-body text-[11px] text-ink-muted">
                Why cited: {source.why_cited}
              </p>
            ) : null}
            <Link
              to={buildSourceHref(collection, source.chunk_id)}
              className="mt-2 inline-block font-ui text-[10px] uppercase tracking-[0.1em] text-claret hover:underline"
            >
              View source →
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}

function renderMeta(source: StudySource, metadataSchema?: CollectionMetadataSchema | null): string {
  return renderMetadataSummary(source.metadata, {
    schema: metadataSchema,
    subLabel: source.sub_question_label,
  });
}
