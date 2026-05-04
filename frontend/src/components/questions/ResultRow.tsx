import { RenderBlocks } from "@/components/shared/render-blocks";
import type { CollectionMetadataSchema, SearchResult } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { buildLevelContext, buildRowMetadataTags, getLevelPill } from "./questionDisplay";

export function ResultRow({
  rank,
  result,
  selected,
  onSelect,
  metadataSchema,
}: {
  rank: number;
  result: SearchResult;
  selected: boolean;
  onSelect: (chunkId: string) => void;
  metadataSchema: CollectionMetadataSchema | null;
}) {
  const level = getLevelPill(result.chunk_level);
  const levelContext = buildLevelContext(
    result.chunk_level,
    result.metadata,
    result.sub_question_label,
  );
  const metaTags = buildRowMetadataTags(result.metadata, metadataSchema);

  return (
    <button
      type="button"
      onClick={() => onSelect(result.chunk_id)}
      aria-pressed={selected}
      className={cn(
        "grid w-full grid-cols-[36px_minmax(0,1fr)_18px] items-start gap-3 rounded-[5px] border border-rule bg-paper-raised p-4 text-left transition-colors hover:border-claret",
        selected && "border-claret bg-[#F2E4DE]",
      )}
    >
      <span
        className={cn(
          "flex h-7 w-7 items-center justify-center rounded-full font-ui text-[12px] font-bold",
          selected ? "bg-claret text-white" : "border border-rule bg-white text-ink-muted",
        )}
      >
        {rank}
      </span>
      <div className="min-w-0">
        <div className="mb-1.5 inline-flex items-center gap-2 font-ui text-[10px] font-bold uppercase tracking-[0.14em] text-ink-muted">
          <span
            className={cn(
              "rounded-[3px] px-1.5 py-px text-[10px] tracking-[0.1em]",
              level.full ? "bg-claret text-white" : "bg-claret-soft text-claret",
            )}
          >
            {level.label}
          </span>
          {levelContext ? <span className="text-ink-muted/75">{levelContext}</span> : null}
        </div>
        <div className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-2 font-display text-[16px] leading-[1.45] text-ink">
          {selected ? (
            <span aria-hidden className="mt-1 text-[13px] text-claret">
              ✦
            </span>
          ) : (
            <span aria-hidden className="hidden" />
          )}
          <div className="min-w-0">
            <RenderBlocks
              blocks={result.render_blocks ?? null}
              mode="compact"
              fallbackText={result.text}
              compactLines={3}
            />
          </div>
        </div>
        {metaTags.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {metaTags.map((tag) => (
              <span
                key={tag}
                className="rounded-[3px] border border-rule-soft bg-white px-2 py-0.5 font-ui text-[11px] tracking-[0.04em] text-ink-muted"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <span aria-hidden className="mt-1 text-right text-[22px] font-light leading-none text-rule">
        ›
      </span>
    </button>
  );
}
