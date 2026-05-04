import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { LoadingSkeleton } from "@/components/shared/LoadingSkeleton";
import { InlineRuns, RenderBlocks, getReferencedMediaIds } from "@/components/shared/render-blocks";
import type { ChunkDetail, CollectionMetadataSchema, MediaRef } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { buildSourceHref } from "@/lib/url/scope";

import { buildDetailMetadataRows } from "./questionDisplay";

export function DetailPanel({
  collection,
  collectionDisplay,
  query: _query,
  rank,
  chunk,
  isLoading,
  metadataSchema,
}: {
  collection: string;
  collectionDisplay: string;
  query: string;
  rank: number | null;
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

  const titleParagraph = chunk.render_blocks?.find((block) => block.type === "paragraph") ?? null;
  const metadataRows = buildDetailMetadataRows({
    collectionDisplay,
    metadata: chunk.metadata,
    schema: metadataSchema,
    subQuestionLabel: chunk.sub_question_label,
  });
  const blockMediaIds = new Set([
    ...getReferencedMediaIds(chunk.render_blocks ?? null),
    ...getReferencedMediaIds(chunk.parent?.render_blocks ?? null),
  ]);
  const remainingMedia = chunk.media.filter((item) => !blockMediaIds.has(item.media_id));

  return (
    <aside className="rounded-md border border-rule bg-paper-raised p-6 lg:sticky lg:top-4">
      <div className="flex items-start gap-3">
        {rank ? (
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-claret font-ui text-[13px] font-bold text-white">
            {rank}
          </div>
        ) : null}
        <h3 className="font-display text-[19px] font-bold leading-[1.35] text-ink">
          {titleParagraph ? <InlineRuns runs={titleParagraph.runs} /> : chunk.text}
        </h3>
      </div>

      <section className="mt-6">
        <div className="section-eyebrow">✦ Matched</div>
        <div className="rounded border border-rule border-l-[3px] border-l-claret bg-claret-soft px-4 py-3 font-display text-[15px] leading-relaxed text-ink">
          <RenderBlocks
            blocks={chunk.render_blocks ?? null}
            mode="full"
            fallbackText={chunk.text}
            media={chunk.media}
          />
        </div>
      </section>

      {chunk.parent ? <ParentQuestionBlock parent={chunk.parent} media={chunk.media} /> : null}

      <section className="mt-6 border-t border-rule-soft pt-5">
        <div className="section-eyebrow text-ink-muted">Question metadata</div>
        <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-6 gap-y-2 font-ui text-[13px]">
          {metadataRows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-ink-muted">{label}</dt>
              <dd className="m-0 text-right font-medium text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {remainingMedia.length > 0 ? <MediaList media={remainingMedia} /> : null}

      <div className="mt-6">
        <Link
          to={buildSourceHref(collection, chunk.chunk_id)}
          state={{ from: location.pathname + location.search }}
          className="inline-flex items-center justify-center gap-2 rounded bg-claret px-4 py-2.5 font-ui text-[12px] font-semibold text-paper-raised transition-colors hover:bg-claret/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 focus-visible:ring-offset-paper-raised"
        >
          <span aria-hidden>📤</span>
          Open shareable source
        </Link>
      </div>
    </aside>
  );
}

type Parent = NonNullable<ChunkDetail["parent"]>;

function ParentQuestionBlock({ parent, media }: { parent: Parent; media: MediaRef[] }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <section className="mt-6">
      <div className="section-eyebrow text-ink-muted">Parent question</div>
      <div
        className={cn(
          "relative mt-2 overflow-hidden font-display text-[15px] leading-relaxed text-ink",
          expanded ? "" : "max-h-[200px]",
        )}
      >
        <RenderBlocks
          blocks={parent.render_blocks ?? null}
          mode="full"
          fallbackText={parent.text}
          media={media}
        />
        {!expanded ? (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-9 bg-gradient-to-b from-transparent to-paper-raised" />
        ) : null}
      </div>
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        className="mt-2 font-ui text-[11px] font-bold uppercase tracking-[0.12em] text-claret hover:underline"
      >
        {expanded ? "Collapse parent" : "Show full parent →"}
      </button>
    </section>
  );
}

function MediaList({ media }: { media: MediaRef[] }) {
  return (
    <div className="mt-4 flex flex-col gap-3">
      {media.map((item, index) => (
        <figure
          key={item.media_id}
          className="overflow-hidden rounded-sm border border-rule-soft bg-paper"
        >
          {item.access_url ? (
            <div className="aspect-[4/3] w-full bg-paper-sunken">
              <img
                src={item.access_url}
                alt={`Question media ${index + 1}`}
                className="h-full w-full object-contain"
              />
            </div>
          ) : (
            <div className="flex aspect-[4/3] w-full items-center justify-center p-4 font-ui text-xs text-ink-muted">
              Media unavailable
            </div>
          )}
        </figure>
      ))}
    </div>
  );
}
