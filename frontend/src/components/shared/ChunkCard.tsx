import type { ReactNode } from "react";
import { useState } from "react";
import { Chip } from "@/components/shared/Chip";
import { RenderBlocks, getReferencedMediaIds } from "@/components/shared/render-blocks";
import type { BlockIndicator } from "@/components/shared/render-blocks";
import { buildMetadataFallbackIndicators } from "@/components/shared/buildMetadataFallbackIndicators";
import type { CollectionMetadataSchema, MediaRef, RenderBlock } from "@/lib/api/types";
import { cn } from "@/lib/cn";
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
    "block w-full rounded-sm border-l-4 border-l-transparent px-3 py-2.5 text-left",
    onClick && "hover:bg-paper-raised",
    isSub && "ml-5",
    selected && "selectable-selected",
  );

  const fallbackIndicators = chunk.render_blocks?.length
    ? null
    : buildMetadataFallbackIndicators(chunk.metadata);

  const metaChips = buildMetaChipsFromSchema(
    chunk.metadata,
    metadataSchema,
    chunk.sub_question_label,
  );

  const content = (
    <>
      <RenderBlocks
        blocks={chunk.render_blocks ?? null}
        mode="compact"
        fallbackText={chunk.text}
        compactLines={3}
      />
      {metaChips.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {metaChips.map((chip) => (
            <Chip key={chip.id} variant="meta">
              {chip.label}
            </Chip>
          ))}
        </div>
      ) : null}
      {fallbackIndicators && fallbackIndicators.length > 0 ? (
        <FallbackIndicatorList indicators={fallbackIndicators} />
      ) : null}
    </>
  );

  if (!onClick) return <div className={className}>{content}</div>;
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
  const blockMediaIds = new Set([
    ...getReferencedMediaIds(chunk.render_blocks ?? null),
    ...getReferencedMediaIds(parent?.render_blocks ?? null),
  ]);
  const remainingMedia = chunk.media.filter((m) => !blockMediaIds.has(m.media_id));
  // Spec §"Detail panel restructure": eyebrow renders sub_question_label literally,
  // or "Matched question" when null.
  const eyebrowLabel = chunk.sub_question_label ?? "Matched question";
  const metaChips = buildMetaChipsFromSchema(chunk.metadata, metadataSchema, null);

  return (
    <article className="rounded-sm bg-paper-raised p-5">
      <div className="section-eyebrow">{eyebrowLabel}</div>
      <RenderBlocks
        blocks={chunk.render_blocks ?? null}
        mode="full"
        fallbackText={chunk.text}
        media={chunk.media}
        className="mt-2"
      />
      {metaChips.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1">
          {metaChips.map((chip) => (
            <Chip key={chip.id} variant="meta">
              {chip.label}
            </Chip>
          ))}
        </div>
      ) : null}
      {parent ? <ParentCollapsible parent={parent} media={chunk.media} /> : null}
      {remainingMedia.length > 0 ? <MediaList media={remainingMedia} /> : null}
      {footer ? <div className="mt-4 border-t border-rule pt-3">{footer}</div> : null}
    </article>
  );
}

type FullParent = NonNullable<Extract<ChunkCardProps, { mode: "full" }>["parent"]>;

function ParentCollapsible({ parent, media }: { parent: FullParent; media: MediaRef[] }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <section className="mt-5 border-t border-rule pt-4">
      <div className="section-eyebrow">Parent question</div>
      <div
        className={cn(
          "mt-1 text-[14px] text-ink-muted overflow-hidden",
          expanded ? "" : "max-h-24",
        )}
      >
        <RenderBlocks
          blocks={parent.render_blocks ?? null}
          mode="full"
          fallbackText={parent.text}
          media={media}
        />
      </div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="mt-2 font-ui text-[11px] uppercase tracking-widest text-claret hover:underline"
      >
        {expanded ? "Collapse parent" : "Show full parent"}
      </button>
    </section>
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

function buildMetaChipsFromSchema(
  metadata: Record<string, unknown>,
  schema: CollectionMetadataSchema | null | undefined,
  subLabel: string | null,
): { id: string; label: string }[] {
  const out: { id: string; label: string }[] = [];
  if (subLabel) out.push({ id: "sub-question-label", label: `Part (${subLabel})` });
  if (!schema) return out;
  for (const field of schema.fields) {
    if (!field.exposed) continue;
    const value = metadata[field.key];
    if (value === null || value === undefined || value === "") continue;
    out.push({ id: field.key, label: `${field.label}: ${value}` });
  }
  return out;
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
