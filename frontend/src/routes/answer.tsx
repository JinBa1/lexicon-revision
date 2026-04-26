import { useCallback, useMemo, useRef, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { AnswerBody } from "@/components/answer/AnswerBody";
import { AnswerStatusBanner } from "@/components/answer/AnswerStatusBanner";
import { LimitationsBlock } from "@/components/answer/LimitationsBlock";
import { PatternsList } from "@/components/answer/PatternsList";
import { RetrievalFooter } from "@/components/answer/RetrievalFooter";
import { SourcesGrid } from "@/components/answer/SourcesGrid";
import { HeaderEcho } from "@/components/questions/HeaderEcho";
import { InvalidFiltersState } from "@/components/questions/InvalidFiltersState";
import { Button } from "@/components/shared/Button";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingSkeleton } from "@/components/shared/LoadingSkeleton";
import { isApiError } from "@/lib/api/errors";
import type {
  CollectionAccessState,
  CollectionMetadataSchema,
  FilterCondition,
  StudyAnswerStatus,
} from "@/lib/api/types";
import { useCollections } from "@/lib/hooks/useCollections";
import { useStudy } from "@/lib/hooks/useStudy";
import { useUrlState } from "@/lib/hooks/useUrlState";
import { buildQuestionsHref } from "@/lib/url/scope";

export function AnswerRoute() {
  const { collection: collectionName = "" } = useParams<{ collection: string }>();
  const [searchParams] = useSearchParams();
  const { data: collections = [], isLoading: collectionsLoading } = useCollections();

  const active = useMemo(
    () => collections.find((collection) => collection.name === collectionName) ?? null,
    [collections, collectionName],
  );
  const schema = active?.metadata_schema ?? null;
  const { query, filterParse } = useUrlState(schema);
  const delayStudyForSchema = collectionsLoading && searchParams.has("filter");

  if (filterParse.ok === false) {
    return (
      <>
        <HeaderEcho
          key={`${query}:invalid`}
          page="answer"
          collectionName={collectionName}
          initialQuery={query}
          initialFilters={[]}
        />
        <AnswerMain>
          <InvalidFiltersState
            collectionName={collectionName}
            offendingField={filterParse.offending_field}
          />
        </AnswerMain>
      </>
    );
  }

  return (
    <AnswerContent
      collectionName={collectionName}
      filters={filterParse.conditions}
      query={query}
      schema={schema}
      activeAccessState={active?.access_state ?? null}
      delayStudyForSchema={delayStudyForSchema}
    />
  );
}

function AnswerContent({
  collectionName,
  filters,
  query,
  schema,
  activeAccessState,
  delayStudyForSchema,
}: {
  collectionName: string;
  filters: FilterCondition[];
  query: string;
  schema: CollectionMetadataSchema | null;
  activeAccessState: CollectionAccessState | null;
  delayStudyForSchema: boolean;
}) {
  const navigate = useNavigate();
  const sourceRefs = useRef(new Map<string, HTMLElement | null>());

  const registerRef = useCallback((chunkId: string, el: HTMLElement | null) => {
    sourceRefs.current.set(chunkId, el);
  }, []);

  const onCitationActivate = useCallback((chunkId: string) => {
    const el = sourceRefs.current.get(chunkId);
    if (!el) return;

    const duration = 900;
    const removeHighlight = () => el.classList.remove("citation-highlighted");

    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("citation-highlighted");
    const animation = el.animate?.(
      [{ boxShadow: "0 0 0 2px #7E2E2E" }, { boxShadow: "0 0 0 0 transparent" }],
      {
        duration,
        easing: "ease-out",
      },
    );
    if (animation) {
      void animation.finished.finally(removeHighlight);
      return;
    }
    window.setTimeout(removeHighlight, duration);
  }, []);

  const hasQuery = query.trim().length > 0;
  const enabled = hasQuery && !delayStudyForSchema;
  const { data, isLoading, isError, error, refetch } = useStudy({
    collection: collectionName,
    query,
    filters,
    enabled,
  });

  const chunkIdToPosition = useMemo(() => {
    const map = new Map<string, number>();
    data?.sources.forEach((source, index) => map.set(source.chunk_id, index + 1));
    return map;
  }, [data]);

  const header = (
    <HeaderEcho
      key={`${query}:${JSON.stringify(filters)}`}
      page="answer"
      collectionName={collectionName}
      initialQuery={query}
      initialFilters={filters}
    />
  );

  if (
    isError &&
    isApiError(error) &&
    error.status === 403 &&
    activeAccessState === "locked_wrong_affiliation"
  ) {
    const next = new URLSearchParams({
      explain: "wrong-affiliation",
      collection: collectionName,
    });
    return <Navigate to={`/?${next.toString()}`} replace />;
  }

  if (isError && isApiError(error) && error.status === 422) {
    return (
      <>
        {header}
        <AnswerMain>
          <InvalidFiltersState collectionName={collectionName} />
        </AnswerMain>
      </>
    );
  }

  return (
    <>
      {header}
      <AnswerMain>
        {!hasQuery ? (
          <section className="rounded-sm border border-rule bg-paper-raised px-6 py-10 text-center">
            <h1 className="font-display text-xl font-semibold text-claret">
              Ask a question to generate an answer
            </h1>
            <p className="mx-auto mt-2 max-w-prose font-body text-sm leading-relaxed text-ink-muted">
              Enter a topic or exam-style prompt above to get a grounded answer from this
              collection.
            </p>
          </section>
        ) : delayStudyForSchema ? (
          <LoadingSkeleton variant="prose" count={8} />
        ) : isLoading ? (
          <LoadingSkeleton variant="prose" count={8} />
        ) : isError && isApiError(error) && error.status === 403 ? (
          <ErrorState
            title="Access has been revoked"
            detail="Your account no longer has access to this collection. Pick another collection or return home."
            actions={<Button onClick={() => navigate("/")}>Back to home</Button>}
          />
        ) : isError ? (
          <ErrorState
            title="Couldn't generate an answer"
            detail="The study request failed. Try again in a moment."
            actions={
              <Button variant="primary" onClick={() => refetch()}>
                Retry
              </Button>
            }
          />
        ) : data ? (
          <>
            <section className="border-b border-rule pb-3">
              <div className="section-eyebrow">Question</div>
              <h1 className="mt-1 font-display text-xl text-ink">{data.query}</h1>
            </section>
            <AnswerStatusBanner status={data.answer_status} />
            <div className="mt-4 space-y-4">
              <AnswerBody overview={data.answer.overview} />
              <PatternsList
                patterns={data.answer.patterns}
                chunkIdToPosition={chunkIdToPosition}
                onCitationActivate={onCitationActivate}
              />
              <LimitationsBlock limitations={data.answer.limitations} />
            </div>
            <RetrievalFooter retrieval={data.retrieval} />
            <SourcesGrid
              collection={collectionName}
              sources={data.sources}
              highlightedChunkId={null}
              metadataSchema={schema}
              registerRef={registerRef}
            />
            {shouldShowQuestionsFallback(data.answer_status) ? (
              <div className="mt-6 rounded-sm border border-rule bg-paper-raised p-4 text-center">
                <Link
                  to={buildQuestionsHref({ collection: collectionName, query, filters })}
                  className="font-display text-[13px] text-claret hover:underline"
                >
                  Retrieve matching questions instead
                </Link>
              </div>
            ) : null}
          </>
        ) : null}
      </AnswerMain>
    </>
  );
}

function AnswerMain({ children }: { children: ReactNode }) {
  return <main className="mx-auto max-w-4xl px-6 py-10">{children}</main>;
}

function shouldShowQuestionsFallback(status: StudyAnswerStatus): boolean {
  return (
    status === "insufficient_evidence" ||
    status === "generation_failed" ||
    status === "retrieval_failed"
  );
}
