import { useCallback, useEffect, useMemo, useRef, type ReactNode } from "react";
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
  StudyResponse,
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
  const highlightTimeoutRef = useRef<number | null>(null);
  const highlightTokenRef = useRef(0);
  const highlightedElementRef = useRef<HTMLElement | null>(null);

  const registerRef = useCallback((chunkId: string, el: HTMLElement | null) => {
    sourceRefs.current.set(chunkId, el);
  }, []);

  const onCitationActivate = useCallback((chunkId: string) => {
    const el = sourceRefs.current.get(chunkId);
    if (!el) return;

    const duration = 900;
    if (highlightTimeoutRef.current !== null) {
      window.clearTimeout(highlightTimeoutRef.current);
      highlightTimeoutRef.current = null;
    }
    highlightedElementRef.current?.classList.remove("citation-highlighted");

    const token = highlightTokenRef.current + 1;
    highlightTokenRef.current = token;
    highlightedElementRef.current = el;
    const removeHighlight = () => {
      if (highlightTokenRef.current !== token) return;
      el.classList.remove("citation-highlighted");
      if (highlightedElementRef.current === el) {
        highlightedElementRef.current = null;
      }
    };

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
    highlightTimeoutRef.current = window.setTimeout(removeHighlight, duration);
  }, []);

  useEffect(() => {
    return () => {
      if (highlightTimeoutRef.current !== null) {
        window.clearTimeout(highlightTimeoutRef.current);
      }
    };
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

  if (isError && isApiError(error) && error.status === 429) {
    return (
      <>
        {header}
        <AnswerMain>
          <ErrorState
            title="Get answer limit reached"
            detail="Too many Get answer requests. Try again later."
          />
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
            <div
              data-testid="answer-result-panel"
              className="rounded-[4px] border border-rule bg-paper-raised px-6 py-8 shadow-[0_12px_35px_rgba(0,0,0,0.04)] sm:px-10 lg:px-12"
            >
              <section className="mb-8 border-b border-rule pb-8">
                <div className="font-ui text-[10px] font-bold uppercase tracking-[0.2em] text-claret">
                  The Question
                </div>
                <h1 className="mt-3 font-display text-[28px] font-bold leading-[1.2] text-ink sm:text-[34px]">
                  {data.query}
                </h1>
              </section>
              <AnswerStatusBanner status={data.answer_status} />
              <div className="space-y-0">
                <AnswerBody overview={data.answer.overview} />
                <LimitationsBlock limitations={data.answer.limitations} />
                <PatternsList
                  patterns={data.answer.patterns}
                  chunkIdToPosition={chunkIdToPosition}
                  onCitationActivate={onCitationActivate}
                />
              </div>
              <RetrievalFooter retrieval={data.retrieval} />
            </div>
            <SourcesGrid
              collection={collectionName}
              sources={data.sources}
              highlightedChunkId={null}
              metadataSchema={schema}
              registerRef={registerRef}
            />
            {shouldShowQuestionsFallback(data.answer_status, data.planning.intent) ? (
              <div className="mt-10 rounded-[4px] border border-rule bg-paper-raised px-6 py-4 text-center">
                <Link
                  to={buildQuestionsHref({ collection: collectionName, query, filters })}
                  className="font-display text-[15px] text-claret hover:underline"
                >
                  Retrieve matching questions instead →
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
  return <main className="mx-auto max-w-[1240px] px-6 py-8 pb-24 sm:px-10">{children}</main>;
}

function shouldShowQuestionsFallback(
  status: StudyAnswerStatus,
  intent: StudyResponse["planning"]["intent"],
): boolean {
  if (
    status === "insufficient_evidence" ||
    status === "generation_failed" ||
    status === "retrieval_failed"
  ) {
    return true;
  }
  // no_corpus_answer is terminal except for ambiguous, which is recoverable
  return status === "no_corpus_answer" && intent === "ambiguous";
}
