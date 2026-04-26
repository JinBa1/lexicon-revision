import { Link, useLocation } from "react-router-dom";
import { Chip } from "@/components/shared/Chip";
import { RenderBlocks } from "@/components/shared/render-blocks";
import type { CollectionMetadataSchema, StudySource } from "@/lib/api/types";
import {
  formatMetadataValue,
  isRenderableValue,
  resolveMetadataFieldValue,
} from "@/lib/metadata/render";
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
  const location = useLocation();

  if (sources.length === 0) return null;
  return (
    <div className="mt-6">
      <div className="my-3 flex items-center gap-3">
        <span className="section-eyebrow">Sources</span>
        <span className="h-px flex-1 bg-rule" />
      </div>
      <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sources.map((source, i) => {
          const metaChips = buildMetaChips(
            source.metadata,
            metadataSchema,
            source.sub_question_label,
          );

          return (
            <li
              key={source.chunk_id}
              ref={(el) => registerRef(source.chunk_id, el)}
              className={`rounded-sm border p-3 ${
                highlightedChunkId === source.chunk_id
                  ? "border-claret bg-claret-soft"
                  : "border-rule bg-paper-raised"
              }`}
            >
              <div className="section-eyebrow">{i + 1}</div>
              <RenderBlocks
                blocks={source.excerpt_blocks}
                mode="compact"
                fallbackText={source.excerpt}
                compactLines={4}
                className="mt-1"
              />
              {metaChips.length > 0 ? (
                <div className="mt-2 flex flex-wrap gap-1">
                  {metaChips.map((chip) => (
                    <Chip key={chip.key} variant="meta">
                      {chip.label}
                    </Chip>
                  ))}
                </div>
              ) : null}
              {source.why_cited ? (
                <div className="mt-3 border-t border-rule-soft pt-2">
                  <div className="section-eyebrow">Why cited</div>
                  <p className="mt-1 font-body text-[12.5px] text-ink">{source.why_cited}</p>
                </div>
              ) : null}
              <Link
                to={buildSourceHref(collection, source.chunk_id)}
                state={{ from: location.pathname + location.search }}
                className="mt-2 inline-block font-ui text-[10px] uppercase tracking-[0.1em] text-claret hover:underline"
              >
                View source →
              </Link>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

type MetaChip = {
  key: string;
  label: string;
};

function buildMetaChips(
  metadata: Record<string, unknown>,
  metadataSchema: CollectionMetadataSchema | null | undefined,
  sub_question_label: string | null,
): MetaChip[] {
  const chips: MetaChip[] = [];
  const normalizedSubLabel = normalizeSubQuestionLabel(sub_question_label);
  if (normalizedSubLabel) {
    chips.push({ key: "sub-question-label", label: `Part (${normalizedSubLabel})` });
  }
  if (!metadataSchema) return chips;

  for (const field of metadataSchema.fields) {
    if (!field.exposed) continue;
    const value = resolveMetadataFieldValue(metadata, field.key, field.source);
    if (!isRenderableValue(value)) continue;
    chips.push({ key: field.key, label: `${field.label}: ${formatMetadataValue(value)}` });
  }

  return chips;
}

function normalizeSubQuestionLabel(sub_question_label: string | null): string | null {
  const trimmed = sub_question_label?.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("(") && trimmed.endsWith(")")) return trimmed.slice(1, -1).trim();
  return trimmed;
}
