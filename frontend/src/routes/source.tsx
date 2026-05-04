import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useState } from "react";

import { CopyLinkButton } from "@/components/source/CopyLinkButton";
import { Button } from "@/components/shared/Button";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingSkeleton } from "@/components/shared/LoadingSkeleton";
import { RenderBlocks, getReferencedMediaIds } from "@/components/shared/render-blocks";
import { isApiError } from "@/lib/api/errors";
import type { CollectionMetadataSchema, ChunkDetail, MediaRef } from "@/lib/api/types";
import { useChunk } from "@/lib/hooks/useChunk";
import { useCollections } from "@/lib/hooks/useCollections";
import {
  formatMetadataValue,
  isRenderableValue,
  resolveMetadataFieldValue,
} from "@/lib/metadata/render";
import { cn } from "@/lib/cn";
import { buildQuestionsHref } from "@/lib/url/scope";

type MetaChip = {
  key: string;
  label: string;
};

export function SourceRoute() {
  const { collection: collectionName = "", chunkId = "" } = useParams<{
    collection: string;
    chunkId: string;
  }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [parentExpanded, setParentExpanded] = useState(false);
  const { data: collections = [] } = useCollections();
  const { data, isLoading, isError, error, refetch } = useChunk({
    collection: collectionName,
    chunkId,
  });

  const previousFrom = (location.state as { from?: string } | null)?.from;
  const fallbackHref = buildQuestionsHref({
    collection: collectionName,
    query: "",
    filters: [],
  });
  const previousHref = previousFrom ?? fallbackHref;
  const previousLabel = previousFrom ? "Back to results" : "Back to collection";
  const activeCollection = collections.find((collection) => collection.name === collectionName);
  const metadataSchema = activeCollection?.metadata_schema ?? null;
  const sharePath = `${location.pathname}${location.search}${location.hash}`;
  const shareUrl = `${window.location.origin}${sharePath}`;

  return (
    <main className="mx-auto max-w-[820px] px-6 py-9 pb-20 sm:px-8">
      {isLoading ? (
        <LoadingSkeleton variant="prose" count={8} />
      ) : isError && isApiError(error) && error.status === 404 ? (
        <ErrorState
          title="Source not found"
          detail={`"${chunkId}" is no longer in ${collectionName}.`}
          actions={<Button onClick={() => navigate(previousHref)}>{previousLabel}</Button>}
        />
      ) : isError && isApiError(error) && error.status === 403 ? (
        <ErrorState
          title="Access denied"
          actions={<Button onClick={() => navigate("/")}>Back to home</Button>}
        />
      ) : isError ? (
        <ErrorState
          title="Couldn't load source"
          actions={
            <Button variant="primary" onClick={() => refetch()}>
              Retry
            </Button>
          }
        />
      ) : data ? (
        <SourceContent
          data={data}
          metadataSchema={metadataSchema}
          parentExpanded={parentExpanded}
          previousLabel={previousLabel}
          shareUrl={shareUrl}
          onBack={() => navigate(previousHref)}
          onToggleParent={() => setParentExpanded((expanded) => !expanded)}
        />
      ) : null}
    </main>
  );
}

function SourceContent({
  data,
  metadataSchema,
  parentExpanded,
  previousLabel,
  shareUrl,
  onBack,
  onToggleParent,
}: {
  data: ChunkDetail;
  metadataSchema: CollectionMetadataSchema | null;
  parentExpanded: boolean;
  previousLabel: string;
  shareUrl: string;
  onBack: () => void;
  onToggleParent: () => void;
}) {
  const metaChips = buildMetaChips(data.metadata, metadataSchema, data.sub_question_label);
  const blockMediaIds = new Set([
    ...getReferencedMediaIds(data.render_blocks),
    ...getReferencedMediaIds(data.parent?.render_blocks ?? null),
  ]);
  const remainingMedia = data.media.filter(
    (item) => item.kind === "image" && !blockMediaIds.has(item.media_id),
  );

  return (
    <>
      <Button
        variant="text"
        className="font-ui text-[12.5px] font-semibold text-claret"
        onClick={onBack}
      >
        {`← ${previousLabel}`}
      </Button>

      <section
        data-testid="source-result-panel"
        className="mt-7 rounded-[4px] border border-rule bg-paper-raised px-6 py-7 shadow-[0_12px_35px_rgba(0,0,0,0.04)] sm:px-9 sm:py-8"
      >
        <div>
          <h1 className="section-eyebrow tracking-[0.2em] text-claret">Shareable Source</h1>
          {metaChips.length > 0 ? <SourceMetaTags chips={metaChips} /> : null}
          <div className="mt-5">
            <CopyLinkButton url={shareUrl} />
          </div>
        </div>

        <article
          data-testid="source-anchor-block"
          className="mt-9 select-text rounded border border-rule border-l-[3px] border-l-claret bg-claret-active px-7 py-6"
        >
          <RenderBlocks
            blocks={data.render_blocks}
            mode="full"
            fallbackText={data.text}
            media={data.media}
            className="text-[17px] leading-[1.65]"
          />
        </article>

        {data.parent ? (
          <section className="mt-10 border-t border-rule pt-7">
            <div className="section-eyebrow tracking-[0.2em] text-ink-muted">Parent question</div>
            <div
              data-testid="source-parent-body"
              className={cn(
                "relative mt-3 overflow-hidden text-ink",
                parentExpanded ? "" : "max-h-36",
              )}
            >
              <RenderBlocks
                blocks={data.parent.render_blocks}
                mode="full"
                fallbackText={data.parent.text}
                media={data.media}
                className="text-[16px] leading-[1.7]"
              />
            </div>
            <button
              type="button"
              onClick={onToggleParent}
              aria-expanded={parentExpanded}
              className="mt-6 inline-flex items-center gap-1 font-ui text-[11px] font-bold uppercase tracking-[0.14em] text-claret hover:underline"
            >
              {parentExpanded ? "↑ Collapse parent" : "Show full parent →"}
            </button>
          </section>
        ) : null}

        {remainingMedia.length > 0 ? <MediaList media={remainingMedia} /> : null}
      </section>
    </>
  );
}

function SourceMetaTags({ chips }: { chips: MetaChip[] }) {
  return (
    <div className="mt-5 flex flex-wrap gap-1.5">
      {chips.map((chip) => (
        <span
          key={chip.key}
          className="rounded-[3px] border border-rule bg-paper-sunken px-2.5 py-[3px] font-ui text-[11px] font-medium tracking-[0.04em] text-ink"
        >
          {chip.label}
        </span>
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
              loading="lazy"
              width={960}
              height={640}
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

function buildMetaChips(
  metadata: Record<string, unknown>,
  metadataSchema: CollectionMetadataSchema | null,
  subQuestionLabel: string | null,
): MetaChip[] {
  const chips: MetaChip[] = [];
  const normalizedSubLabel = normalizeSubQuestionLabel(subQuestionLabel);
  if (normalizedSubLabel) {
    chips.push({ key: "sub-question-label", label: `Part (${normalizedSubLabel})` });
  }
  if (!metadataSchema) return chips;

  for (const field of metadataSchema.fields) {
    if (!field.exposed) continue;
    const value = resolveMetadataFieldValue(metadata, field.key, field.source);
    if (!isRenderableValue(value)) continue;
    chips.push({
      key: field.key,
      label: formatSourceMetaLabel(field.label, formatMetadataValue(value)),
    });
  }

  return chips;
}

function formatSourceMetaLabel(label: string, value: string): string {
  const normalized = label.trim().toLowerCase();

  if (normalized === "year" || normalized === "academic year") {
    return value;
  }

  if (normalized === "paper") {
    return value;
  }

  if (normalized === "question") {
    return formatQuestionTag(value);
  }

  if (normalized === "marks") {
    return `${value} marks`;
  }

  return `${label}: ${value}`;
}

function formatQuestionTag(value: string): string {
  const trimmed = value.trim();
  const numeric = trimmed.match(/\d+/)?.[0];
  if (numeric) return `Q${numeric}`;
  if (trimmed.toLowerCase().startsWith("q")) return trimmed.toUpperCase();
  return `Q ${trimmed}`;
}

function normalizeSubQuestionLabel(subQuestionLabel: string | null): string | null {
  const trimmed = subQuestionLabel?.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("(") && trimmed.endsWith(")")) return trimmed.slice(1, -1).trim();
  return trimmed;
}
