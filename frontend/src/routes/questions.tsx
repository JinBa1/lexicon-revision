import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { EmptyQuestions } from "@/components/questions/EmptyQuestions";
import { HeaderEcho } from "@/components/questions/HeaderEcho";
import { InvalidFiltersState } from "@/components/questions/InvalidFiltersState";
import { DetailPanel } from "@/components/questions/DetailPanel";
import { ResultList } from "@/components/questions/ResultList";
import { Button } from "@/components/shared/Button";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingSkeleton } from "@/components/shared/LoadingSkeleton";
import { isApiError } from "@/lib/api/errors";
import { useChunk } from "@/lib/hooks/useChunk";
import { useCollections } from "@/lib/hooks/useCollections";
import { useResultListKeyboardNav } from "@/lib/hooks/useResultListKeyboardNav";
import { useSearch } from "@/lib/hooks/useSearch";
import { useUrlState } from "@/lib/hooks/useUrlState";
import { buildSourceHref } from "@/lib/url/scope";

export function QuestionsRoute() {
  const { collection: collectionName = "" } = useParams<{ collection: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: collections = [] } = useCollections();

  const active = useMemo(
    () => collections.find((collection) => collection.name === collectionName) ?? null,
    [collections, collectionName],
  );
  const urlState = useUrlState(active?.metadata_schema ?? null);
  const query = urlState.query.trim();
  const filters = urlState.filterParse.ok ? urlState.filterParse.conditions : [];
  const hasValidFilters = urlState.filterParse.ok;

  const search = useSearch({
    collection: collectionName,
    query,
    filters,
    enabled: query.length > 0 && hasValidFilters,
  });

  const focus = searchParams.get("focus");
  const results = search.data?.results ?? [];
  const selectedChunkId = focus ?? results[0]?.chunk_id ?? null;
  const chunk = useChunk(
    selectedChunkId === null ? null : { collection: collectionName, chunkId: selectedChunkId },
  );

  const setFocus = useCallback(
    (chunkId: string | null) => {
      const next = new URLSearchParams(searchParams);
      if (chunkId === null) {
        next.delete("focus");
      } else {
        next.set("focus", chunkId);
      }
      setSearchParams(next);
    },
    [searchParams, setSearchParams],
  );

  const location = useLocation();
  const isMobile = useIsMobile();
  useResultListKeyboardNav({
    results,
    selectedChunkId,
    onFocus: setFocus,
    onNavigate: (chunkId) => {
      navigate(buildSourceHref(collectionName, chunkId), {
        state: { from: location.pathname + location.search },
      });
    },
    onCloseOverlay: () => setFocus(null),
    isMobileOverlayOpen: focus !== null && isMobile,
  });

  useEffect(() => {
    if (search.data === undefined || focus === null) return;
    if (search.data.results.some((result) => result.chunk_id === focus)) return;

    const next = new URLSearchParams(searchParams);
    next.delete("focus");
    setSearchParams(next, { replace: true });
  }, [focus, search.data, searchParams, setSearchParams]);

  const clearFilters = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    next.delete("filter");
    next.delete("focus");
    setSearchParams(next);
  }, [searchParams, setSearchParams]);

  const switchCollection = useCallback(() => {
    const params = new URLSearchParams({
      scopePicker: "1",
      page: "questions",
    });
    if (query.length > 0) {
      params.set("q", query);
    }
    navigate(`/?${params.toString()}`);
  }, [navigate, query]);

  const header = (
    <HeaderEcho
      key={`${urlState.query}:${searchParams.getAll("filter").join("\u0000")}`}
      page="questions"
      collectionName={collectionName}
      initialQuery={urlState.query}
      initialFilters={filters}
    />
  );

  if (!hasValidFilters) {
    return (
      <QuestionsShell header={header}>
        <InvalidFiltersState
          collectionName={collectionName}
          offendingField={urlState.filterParse.offending_field}
        />
      </QuestionsShell>
    );
  }

  if (search.isError && isApiError(search.error)) {
    if (search.error.status === 403 && active?.access_state === "locked_wrong_affiliation") {
      const params = new URLSearchParams({
        explain: "wrong-affiliation",
        collection: collectionName,
      });
      return <Navigate to={`/?${params.toString()}`} replace />;
    }

    if (search.error.status === 422) {
      return (
        <QuestionsShell header={header}>
          <InvalidFiltersState collectionName={collectionName} />
        </QuestionsShell>
      );
    }

    if (search.error.status === 429) {
      return (
        <QuestionsShell header={header}>
          <ErrorState
            title="Find questions limit reached"
            detail="Too many Find questions requests. Try again later."
          />
        </QuestionsShell>
      );
    }

    if (search.error.status === 403) {
      return (
        <QuestionsShell header={header}>
          <ErrorState
            title="Access to this collection changed"
            detail="Your account no longer has access to this collection. Pick another collection or return home."
            actions={
              <Button variant="primary" onClick={() => navigate("/")}>
                Back to home
              </Button>
            }
          />
        </QuestionsShell>
      );
    }
  }

  if (query.length === 0) {
    return (
      <QuestionsShell header={header}>
        <EmptyState
          title="Search for a question pattern"
          detail="Enter a topic or exam phrase above to find matching past-paper questions."
        />
      </QuestionsShell>
    );
  }

  if (search.isError) {
    return (
      <QuestionsShell header={header}>
        <ErrorState
          title="Couldn't load matching questions"
          detail="The search request failed. Try again in a moment."
          actions={
            <Button variant="primary" onClick={() => search.refetch()}>
              Retry
            </Button>
          }
        />
      </QuestionsShell>
    );
  }

  if (search.isLoading) {
    return (
      <QuestionsShell header={header}>
        <div className="rounded-md border border-rule bg-paper-raised p-4">
          <LoadingSkeleton variant="row" count={6} />
        </div>
      </QuestionsShell>
    );
  }

  if (search.data && search.data.results.length === 0) {
    return (
      <QuestionsShell header={header}>
        <EmptyQuestions
          collectionName={collectionName}
          collectionDisplay={active?.display_name ?? collectionName}
          query={query}
          filters={filters}
          onEditFilters={clearFilters}
          onSwitchCollection={switchCollection}
        />
      </QuestionsShell>
    );
  }

  return (
    <QuestionsShell header={header}>
      <div className="overflow-hidden rounded-md border border-rule bg-paper-raised">
        <div className="grid lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <ResultList
            results={results}
            selectedChunkId={selectedChunkId}
            onSelect={setFocus}
            metadataSchema={active?.metadata_schema ?? null}
          />
          <div className="hidden min-h-[34rem] lg:block">
            <DetailPanel
              collection={collectionName}
              chunk={chunk.data}
              isLoading={chunk.isLoading}
              metadataSchema={active?.metadata_schema ?? null}
            />
          </div>
        </div>
      </div>
      <p className="mt-3 text-center font-ui text-[11px] text-ink-muted">
        Use ↑↓ to move through results · Enter to open source · Esc to close detail (mobile)
      </p>
      {focus !== null ? (
        <div className="fixed inset-0 z-30 overflow-y-auto bg-paper lg:hidden">
          <div className="sticky top-0 z-10 border-b border-rule bg-paper-raised p-3 shadow-sm">
            <Button variant="secondary" onClick={() => setFocus(null)} className="h-12 px-4">
              ← Back to results
            </Button>
          </div>
          <DetailPanel
            collection={collectionName}
            chunk={chunk.data}
            isLoading={chunk.isLoading}
            metadataSchema={active?.metadata_schema ?? null}
          />
        </div>
      ) : null}
    </QuestionsShell>
  );
}

function QuestionsShell({ header, children }: { header: ReactNode; children: ReactNode }) {
  return (
    <>
      {header}
      <main className="mx-auto max-w-6xl px-6 pb-8 pt-1">
        <div className="mt-5">{children}</div>
      </main>
    </>
  );
}

function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window === "undefined" || !window.matchMedia
      ? false
      : window.matchMedia("(max-width: 1023px)").matches,
  );
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(max-width: 1023px)");
    const onChange = () => setIsMobile(mq.matches);
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    }
    mq.addListener(onChange);
    return () => mq.removeListener(onChange);
  }, []);
  return isMobile;
}
