import { useCallback, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { CollectionsGrid } from "@/components/collections/CollectionsGrid";
import { NoAffiliationBanner } from "@/components/collections/NoAffiliationBanner";
import { WrongAffiliationModal } from "@/components/collections/WrongAffiliationModal";
import { Hero } from "@/components/hero/Hero";
import { Button } from "@/components/shared/Button";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingSkeleton } from "@/components/shared/LoadingSkeleton";
import { useAppAuth } from "@/lib/auth/runtime";
import type { CollectionListItem, FilterCondition } from "@/lib/api/types";
import { useCollections } from "@/lib/hooks/useCollections";
import {
  buildAnswerHref,
  buildCollectionHref,
  buildQuestionsHref,
  buildUnlockHref,
} from "@/lib/url/scope";

export function CollectionHomeRoute() {
  const { collection: collectionName = "" } = useParams<{ collection: string }>();
  const [searchParams] = useSearchParams();
  const { isSignedIn } = useAppAuth();
  const navigate = useNavigate();
  const { data: collections = [], isLoading, isError, refetch } = useCollections();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const queryRef = useRef(query);
  const [filters, setFilters] = useState<FilterCondition[]>([]);
  const [wrongAffiliationCollection, setWrongAffiliationCollection] =
    useState<CollectionListItem | null>(null);

  const active = useMemo(
    () => collections.find((collection) => collection.name === collectionName) ?? null,
    [collections, collectionName],
  );

  const buildScopeTarget = useCallback(
    (nextCollectionName: string) => {
      const requestedPage = searchParams.get("page");
      const nextQuery = query.trim();
      if (requestedPage === "answer") {
        return buildAnswerHref({
          collection: nextCollectionName,
          query: nextQuery,
          filters: [],
        });
      }
      if (requestedPage === "questions" || nextQuery.length > 0) {
        return buildQuestionsHref({
          collection: nextCollectionName,
          query: nextQuery,
          filters: [],
        });
      }
      return buildCollectionHref(nextCollectionName);
    },
    [query, searchParams],
  );

  const onPickAccessible = useCallback(
    (collection: CollectionListItem) => {
      setFilters([]);
      navigate(buildScopeTarget(collection.name), { replace: true });
    },
    [buildScopeTarget, navigate],
  );

  const onPickLocked = useCallback(
    (collection: CollectionListItem) => {
      if (collection.access_state === "locked_requires_signin") {
        navigate(buildUnlockHref(collection.name, buildScopeTarget(collection.name)));
        return;
      }
      setWrongAffiliationCollection(collection);
    },
    [buildScopeTarget, navigate],
  );

  const onQueryChange = useCallback((nextQuery: string) => {
    queryRef.current = nextQuery;
    setQuery(nextQuery);
  }, []);

  const submit = useCallback(
    (action: "questions" | "answer") => {
      if (active === null || active.access_state !== "accessible") return;
      const opts = { collection: active.name, query: queryRef.current, filters };
      navigate(action === "questions" ? buildQuestionsHref(opts) : buildAnswerHref(opts));
    },
    [active, filters, navigate],
  );

  if (isLoading) {
    return (
      <main className="mx-auto max-w-5xl px-6 py-12">
        <LoadingSkeleton variant="card" count={3} />
      </main>
    );
  }

  if (isError) {
    return (
      <main className="mx-auto max-w-5xl px-6 py-12">
        <ErrorState
          title="Couldn't load the catalogue"
          actions={
            <Button variant="primary" onClick={() => refetch()}>
              Retry
            </Button>
          }
        />
      </main>
    );
  }

  if (active === null) {
    return (
      <main className="mx-auto max-w-5xl px-6 py-12">
        <ErrorState
          title="Collection not found"
          detail={`"${collectionName}" is not in the catalogue.`}
          actions={
            <Button variant="primary" onClick={() => navigate("/")}>
              Back to home
            </Button>
          }
        />
      </main>
    );
  }

  if (active.access_state === "locked_requires_signin") {
    return <Navigate to={buildUnlockHref(active.name, buildScopeTarget(active.name))} replace />;
  }

  if (active.access_state === "locked_wrong_affiliation") {
    const params = new URLSearchParams({
      explain: "wrong-affiliation",
      collection: active.name,
    });
    return <Navigate to={`/?${params.toString()}`} replace />;
  }

  const anyAccessible = collections.some((collection) => collection.access_state === "accessible");

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <div className="text-center">
        <h1 className="mx-auto max-w-3xl font-display text-4xl font-semibold leading-tight text-ink">
          {active.display_name}
        </h1>
      </div>
      <div className="mt-6">
        <Hero
          mode="landing"
          activeCollection={active}
          query={query}
          filters={filters}
          onQueryChange={onQueryChange}
          onFiltersChange={setFilters}
          onOpenScope={() =>
            document.getElementById("collections-grid")?.scrollIntoView({ behavior: "smooth" })
          }
          onSubmit={submit}
        />
      </div>
      <div id="collections-grid">
        {isSignedIn && !anyAccessible ? (
          <div className="mt-10">
            <NoAffiliationBanner />
          </div>
        ) : null}
        <CollectionsGrid
          collections={collections}
          activeName={active.name}
          isSignedIn={Boolean(isSignedIn)}
          onPickAccessible={onPickAccessible}
          onPickLocked={onPickLocked}
        />
        <WrongAffiliationModal
          collection={wrongAffiliationCollection}
          onClose={() => setWrongAffiliationCollection(null)}
        />
      </div>
    </main>
  );
}
