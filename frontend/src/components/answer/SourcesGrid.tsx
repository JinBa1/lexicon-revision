import { Link, useLocation } from "react-router-dom";

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
    <section className="mt-12">
      <div className="flex items-center gap-6">
        <div className="font-ui text-[10px] font-bold uppercase tracking-[0.2em] text-ink">
          Sources
        </div>
        <span data-testid="sources-heading-rule" className="h-px flex-1 bg-rule" />
      </div>
      <ol className="mt-7 grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
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
              className={`rounded-[4px] border bg-paper-raised p-[18px] transition-all hover:-translate-y-px hover:border-claret hover:shadow-[0_6px_16px_rgba(0,0,0,0.04)] ${
                highlightedChunkId === source.chunk_id
                  ? "border-claret bg-claret-soft"
                  : "border-rule"
              }`}
            >
              <div className="font-ui text-[10px] font-extrabold uppercase tracking-[0.1em] text-ink-muted">
                {i + 1} · Source
              </div>
              <RenderBlocks
                blocks={source.excerpt_blocks}
                mode="compact"
                fallbackText={source.excerpt}
                compactLines={4}
                className="mt-3 text-[14.5px] leading-[1.5]"
              />
              {metaChips.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {metaChips.map((chip) => (
                    <span
                      key={chip.key}
                      className="rounded-[3px] bg-paper-sunken px-2 py-0.5 font-ui text-[10px] font-semibold uppercase tracking-[0.06em] text-ink-muted"
                    >
                      {chip.label}
                    </span>
                  ))}
                </div>
              ) : null}
              {source.why_cited ? (
                <div className="mt-3 border-t border-rule-soft pt-2">
                  <div className="font-ui text-[10px] font-bold uppercase tracking-[0.12em] text-claret">
                    Why cited
                  </div>
                  <p className="mt-1 font-body text-[13px] leading-[1.5] text-ink">
                    {source.why_cited}
                  </p>
                </div>
              ) : null}
              <Link
                to={buildSourceHref(collection, source.chunk_id)}
                state={{ from: location.pathname + location.search }}
                className="mt-3 inline-block font-ui text-[10px] font-bold uppercase tracking-[0.12em] text-claret hover:underline"
              >
                View source →
              </Link>
            </li>
          );
        })}
      </ol>
    </section>
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

  const schemaTags = metadataSchema
    ? metadataSchema.fields
        .filter((field) => field.exposed && isSourceMetaField(field.key, field.label, field.source))
        .map((field): MetaChip | null => {
          const value = resolveMetadataFieldValue(metadata, field.key, field.source);
          if (!isRenderableValue(value)) return null;
          return { key: field.key, label: formatMetadataValue(value) };
        })
        .filter((chip): chip is MetaChip => chip !== null)
    : [];

  if (schemaTags.length > 0) {
    return [...chips, ...schemaTags];
  }

  if (isRenderableValue(metadata.year)) {
    chips.push({ key: "year", label: formatMetadataValue(metadata.year) });
  }
  const paper = metadata.paper_label ?? metadata.paper;
  if (isRenderableValue(paper)) {
    chips.push({ key: "paper", label: formatMetadataValue(paper) });
  }
  return chips;
}

function isSourceMetaField(key: string, label: string, source: string | null): boolean {
  const tokens = [key, label, source ?? ""].map((value) => value.toLowerCase());
  return tokens.some((value) => value === "year" || value === "paper" || value === "paper_label");
}

function normalizeSubQuestionLabel(sub_question_label: string | null): string | null {
  const trimmed = sub_question_label?.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("(") && trimmed.endsWith(")")) return trimmed.slice(1, -1).trim();
  return trimmed;
}
