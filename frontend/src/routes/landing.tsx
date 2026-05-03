import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { CollectionsGrid } from "@/components/collections/CollectionsGrid";
import { NoAffiliationBanner } from "@/components/collections/NoAffiliationBanner";
import { WrongAffiliationModal } from "@/components/collections/WrongAffiliationModal";
import { Hero } from "@/components/hero/Hero";
import { HeroStatusStrip } from "@/components/hero/HeroStatusStrip";
import { SteppedRibbon } from "@/components/hero/SteppedRibbon";
import { Button } from "@/components/shared/Button";
import { EmptyState } from "@/components/shared/EmptyState";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingSkeleton } from "@/components/shared/LoadingSkeleton";
import { useAppAuth } from "@/lib/auth/runtime";
import type { CollectionListItem, FilterCondition } from "@/lib/api/types";
import { useCollections } from "@/lib/hooks/useCollections";
import { buildCollectionHref, buildUnlockHref } from "@/lib/url/scope";

export function LandingRoute() {
  const [searchParams] = useSearchParams();
  const { isSignedIn } = useAppAuth();
  const { data, isLoading, isError, refetch } = useCollections();
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [filters] = useState<FilterCondition[]>([]);
  const [scopeFlash, setScopeFlash] = useState(false);
  const [wrongAffiliationCollection, setWrongAffiliationCollection] =
    useState<CollectionListItem | null>(null);
  const scopeFlashTimeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const navigate = useNavigate();

  const collections = useMemo(() => data ?? [], [data]);
  const anyAccessible = useMemo(
    () => collections.some((collection) => collection.access_state === "accessible"),
    [collections],
  );

  const onPickAccessible = useCallback(
    (collection: CollectionListItem) => {
      const requestedQuery = query.trim();
      navigate(buildCollectionHref(collection.name, { query: requestedQuery }), { replace: true });
    },
    [navigate, query],
  );

  const onPickLocked = useCallback(
    (collection: CollectionListItem) => {
      const requestedQuery = query.trim();
      const returnTo = buildCollectionHref(collection.name, { query: requestedQuery });

      if (collection.access_state === "locked_requires_signin") {
        navigate(buildUnlockHref(collection.name, returnTo));
        return;
      }

      setWrongAffiliationCollection(collection);
    },
    [navigate, query],
  );

  const onScopeMissing = useCallback(() => {
    if (scopeFlashTimeoutRef.current !== null) {
      window.clearTimeout(scopeFlashTimeoutRef.current);
    }

    setScopeFlash(true);
    const grid = document.getElementById("collections");
    grid?.scrollIntoView({ behavior: "smooth", block: "start" });
    scopeFlashTimeoutRef.current = window.setTimeout(() => {
      setScopeFlash(false);
      scopeFlashTimeoutRef.current = null;
    }, 1200);
  }, []);

  useEffect(() => {
    return () => {
      if (scopeFlashTimeoutRef.current !== null) {
        window.clearTimeout(scopeFlashTimeoutRef.current);
      }
    };
  }, []);

  return (
    <main className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:pb-14 lg:pt-[4.5rem]">
      <div className="text-center">
        <div className="font-ui text-[11px] uppercase tracking-widest text-claret">
          PAST-PAPER REVISION
        </div>
        <h1 className="mx-auto mt-3 max-w-5xl font-display text-4xl font-semibold leading-tight text-ink sm:text-5xl lg:text-[4.8rem]">
          Read the question. Then ask yours.
        </h1>
        <p className="mx-auto mt-5 max-w-2xl font-body text-base leading-relaxed text-ink-muted">
          Search a curated archive of university past papers, or get a grounded answer assembled
          from them — every answer cited back to the exact question it came from.
        </p>
      </div>

      <section
        aria-label="Search workflow"
        className="mt-9 overflow-visible rounded-md border border-rule bg-paper-raised shadow-module"
      >
        <SteppedRibbon />
        <Hero
          mode="landing"
          chrome="landing-unified"
          activeCollection={null}
          query={query}
          filters={filters}
          onQueryChange={setQuery}
          onFiltersChange={() => {}}
          onOpenScope={() => {
            document.getElementById("collections")?.scrollIntoView({ behavior: "smooth" });
          }}
          onSubmit={() => {}}
          onScopeMissing={onScopeMissing}
          showScopeRequiredHelper={false}
        />
        <HeroStatusStrip activeCollection={null} chrome="landing-unified" />
        {scopeFlash ? (
          <div
            role="alert"
            className="border-t border-rule-soft bg-claret-soft px-6 py-2 text-center font-display text-sm italic text-claret"
          >
            Please pick a collection first
          </div>
        ) : null}
      </section>

      <div id="collections">
        {isLoading ? (
          <section className="mt-10">
            <LoadingSkeleton variant="card" count={6} />
          </section>
        ) : isError ? (
          <section className="mt-10">
            <ErrorState
              title="Couldn't load the catalogue"
              detail="There was a problem loading collections."
              actions={
                <Button variant="primary" onClick={() => refetch()}>
                  Retry
                </Button>
              }
            />
          </section>
        ) : collections.length === 0 ? (
          <section className="mt-10">
            <EmptyState
              title="No collections are available yet"
              detail="If you're from a supported university, sign in to see yours."
            />
          </section>
        ) : (
          <>
            {isSignedIn && !anyAccessible ? (
              <div className="mt-10">
                <NoAffiliationBanner />
              </div>
            ) : null}
            <CollectionsGrid
              collections={collections}
              activeName={null}
              isSignedIn={Boolean(isSignedIn)}
              onPickAccessible={onPickAccessible}
              onPickLocked={onPickLocked}
            />
            <WrongAffiliationModal
              collection={wrongAffiliationCollection}
              onClose={() => setWrongAffiliationCollection(null)}
            />
          </>
        )}
      </div>
    </main>
  );
}
