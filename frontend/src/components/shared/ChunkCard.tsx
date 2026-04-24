import type { ReactNode } from "react";
import type { CollectionMetadataSchema, MediaRef } from "@/lib/api/types";
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
      parent: { text: string; metadata: Record<string, unknown> } | null;
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
  const content = (
    <>
      <div className="font-ui text-[11px] uppercase tracking-wider text-ink-muted">
        {renderMetadataSummary(chunk.metadata, {
          schema: metadataSchema,
          subLabel: chunk.sub_question_label,
        })}
      </div>
      <p className="mt-1 font-body text-sm italic text-ink">{truncateExcerpt(chunk.text)}</p>
      {chunk.media.length > 0 ? (
        <div className="mt-1 font-ui text-[10px] uppercase tracking-wider text-ink-muted">
          {chunk.media.length} media
        </div>
      ) : null}
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
  return (
    <article className="rounded-sm bg-paper-raised p-5">
      {parent ? (
        <>
          <div className="font-ui text-[10px] uppercase tracking-wider text-ink-muted">
            Parent question
          </div>
          <p className="mt-1 font-body text-sm text-ink-muted">{parent.text}</p>
          <div className="my-4 h-px bg-rule" />
        </>
      ) : null}
      <div className="font-ui text-[10px] uppercase tracking-wider text-ink-muted">
        {renderMetadataSummary(chunk.metadata, {
          schema: metadataSchema,
          subLabel: chunk.sub_question_label,
        })}
      </div>
      <p className="mt-2 max-w-[65ch] font-body text-[15px] leading-relaxed text-ink">
        {chunk.text}
      </p>
      {chunk.media.length > 0 ? <MediaList media={chunk.media} /> : null}
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

function MediaList({ media }: { media: MediaRef[] }) {
  return (
    <div className="mt-4 flex flex-col gap-3">
      {media.map((item) => (
        <figure key={item.media_id} className="rounded-sm border border-rule-soft bg-paper">
          {item.access_url ? (
            <img
              src={item.access_url}
              alt={item.media_id}
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
