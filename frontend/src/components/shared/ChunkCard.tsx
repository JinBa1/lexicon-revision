import type { ReactNode } from "react";
import { Chip } from "@/components/shared/Chip";
import { RenderBlocks, getReferencedMediaIds } from "@/components/shared/render-blocks";
import type { BlockIndicator } from "@/components/shared/render-blocks";
import { buildMetadataFallbackIndicators } from "@/components/shared/buildMetadataFallbackIndicators";
import type { CollectionMetadataSchema, MediaRef, RenderBlock } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { renderMetadataSummary } from "@/lib/metadata/render";
import { truncateExcerpt } from "@/lib/url/query";

type CommonChunk = {
  chunk_id: string;
  chunk_level: "question" | "sub_question";
  parent_chunk_id: string | null;
  sub_question_label: string | null;
  text: string;
  metadata: Record<string, unknown>;
  media: MediaRef[];
  render_blocks?: RenderBlock[] | null;
};

type MetadataDisplayProps = {
  metadataSchema?: CollectionMetadataSchema | null;
};

type ChunkCardProps =
  | ({
      mode: "compact";
      chunk: CommonChunk;
      selected?: boolean;
      onClick?: () => void;
    } & MetadataDisplayProps)
  | ({
      mode: "full";
      chunk: CommonChunk;
      parent: {
        text: string;
        metadata: Record<string, unknown>;
        render_blocks?: RenderBlock[] | null;
      } | null;
      footer?: ReactNode;
    } & MetadataDisplayProps)
  | ({
      mode: "inline";
      chunk: CommonChunk;
    } & MetadataDisplayProps);

export function ChunkCard(props: ChunkCardProps) {
  if (props.mode === "compact") {
    return <CompactChunkCard {...props} />;
  }
  if (props.mode === "full") {
    return <FullChunkCard {...props} />;
  }
  return <InlineChunkCard {...props} />;
}

function CompactChunkCard({
  chunk,
  selected,
  onClick,
  metadataSchema,
}: Extract<ChunkCardProps, { mode: "compact" }>) {
  const isSub = chunk.chunk_level === "sub_question";
  const className = cn(
    "block w-full rounded-sm border border-transparent px-3 py-2.5 text-left",
    onClick && "hover:bg-paper-raised",
    isSub && "ml-5",
    selected && "border-l-2 border-claret bg-claret-soft",
  );
  const fallbackIndicators =
    chunk.render_blocks == null || chunk.render_blocks.length === 0
      ? buildMetadataFallbackIndicators(chunk.metadata)
      : [];
  const content = (
    <>
      <div className="font-ui text-[11px] uppercase tracking-wider text-ink-muted">
        {renderMetadataSummary(chunk.metadata, {
          schema: metadataSchema,
          subLabel: chunk.sub_question_label,
        })}
      </div>
      <RenderBlocks
        blocks={chunk.render_blocks ?? null}
        mode="compact"
        fallbackText={chunk.text}
        compactLines={3}
        className="mt-1"
      />
      <FallbackIndicatorList indicators={fallbackIndicators} />
    </>
  );

  if (!onClick) {
    return <div className={className}>{content}</div>;
  }

  return (
    <button type="button" onClick={onClick} aria-pressed={selected} className={className}>
      {content}
    </button>
  );
}

function FullChunkCard({
  chunk,
  parent,
  footer,
  metadataSchema,
}: Extract<ChunkCardProps, { mode: "full" }>) {
  const referencedMediaIds = getReferencedMediaIds(chunk.render_blocks ?? null);
  const remainingMedia = chunk.media.filter((item) => !referencedMediaIds.has(item.media_id));

  return (
    <article className="rounded-sm bg-paper-raised p-5">
      {parent ? (
        <>
          <div className="font-ui text-[10px] uppercase tracking-wider text-ink-muted">
            Parent question
          </div>
          <RenderBlocks
            blocks={parent.render_blocks ?? null}
            mode="full"
            fallbackText={parent.text}
            className="mt-1 text-sm text-ink-muted"
          />
          <div className="my-4 h-px bg-rule" />
        </>
      ) : null}
      <div className="font-ui text-[10px] uppercase tracking-wider text-ink-muted">
        {renderMetadataSummary(chunk.metadata, {
          schema: metadataSchema,
          subLabel: chunk.sub_question_label,
        })}
      </div>
      <RenderBlocks
        blocks={chunk.render_blocks ?? null}
        mode="full"
        fallbackText={chunk.text}
        media={chunk.media}
        className="mt-2 max-w-[65ch] font-body text-[15px] leading-relaxed text-ink"
      />
      {remainingMedia.length > 0 ? <MediaList media={remainingMedia} /> : null}
      {footer ? <div className="mt-4 border-t border-rule pt-3">{footer}</div> : null}
    </article>
  );
}

function InlineChunkCard({ chunk }: Extract<ChunkCardProps, { mode: "inline" }>) {
  return (
    <span className="inline-block rounded-sm border border-rule bg-paper-raised px-2 py-1 font-body text-xs text-ink">
      {truncateExcerpt(chunk.text, 80)}
    </span>
  );
}

const INDICATOR_LABEL = {
  code: "Contains code",
  table: "Contains table",
  figure: "Contains figure",
} satisfies Record<BlockIndicator["kind"], string>;

function FallbackIndicatorList({ indicators }: { indicators: BlockIndicator[] }) {
  if (indicators.length === 0) {
    return null;
  }

  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {indicators.map((indicator) => (
        <Chip key={indicator.kind} variant="ghost">
          {INDICATOR_LABEL[indicator.kind]}
        </Chip>
      ))}
    </div>
  );
}

function MediaList({ media }: { media: MediaRef[] }) {
  return (
    <div className="mt-4 flex flex-col gap-3">
      {media.map((item, index) => (
        <figure key={item.media_id} className="rounded-sm border border-rule-soft bg-paper">
          {item.access_url ? (
            <img
              src={item.access_url}
              alt={`Question media ${index + 1}`}
              className="mx-auto max-h-96 object-contain"
            />
          ) : (
            <div className="p-4 font-ui text-xs text-ink-muted">Media unavailable</div>
          )}
        </figure>
      ))}
    </div>
  );
}
