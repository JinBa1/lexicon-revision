import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Hero, type HeroSubmitAction } from "@/components/hero/Hero";
import type { FilterCondition } from "@/lib/api/types";
import { useCollections } from "@/lib/hooks/useCollections";
import { buildAnswerHref, buildQuestionsHref } from "@/lib/url/scope";

export function HeaderEcho({
  page,
  collectionName,
  initialQuery,
  initialFilters,
  onFiltersChange,
}: {
  page: "questions" | "answer" | "source";
  collectionName: string;
  initialQuery: string;
  initialFilters: FilterCondition[];
  onFiltersChange?: (next: FilterCondition[]) => void;
}) {
  const navigate = useNavigate();
  const { data: collections = [] } = useCollections();
  const [query, setQuery] = useState(initialQuery);
  const [filters, setFilters] = useState<FilterCondition[]>(initialFilters);

  const active = useMemo(
    () => collections.find((collection) => collection.name === collectionName) ?? null,
    [collections, collectionName],
  );

  const updateFilters = useCallback(
    (next: FilterCondition[]) => {
      setFilters(next);
      onFiltersChange?.(next);
    },
    [onFiltersChange],
  );

  const submit = useCallback(
    (action: HeroSubmitAction) => {
      if (active === null) return;

      const opts = {
        collection: active.name,
        query: query.trim(),
        filters,
      };
      navigate(action === "questions" ? buildQuestionsHref(opts) : buildAnswerHref(opts));
    },
    [active, filters, navigate, query],
  );

  const switchScope = useCallback(() => {
    const params = new URLSearchParams({
      scopePicker: "1",
      page,
    });
    const trimmedQuery = query.trim();
    if (trimmedQuery.length > 0) {
      params.set("q", trimmedQuery);
    }

    navigate(`/?${params.toString()}`);
  }, [navigate, page, query]);

  return (
    <div className="border-b border-rule bg-paper-raised">
      <div className="mx-auto max-w-6xl px-6 py-3">
        <Hero
          mode="header-echo"
          activeCollection={active}
          query={query}
          filters={filters}
          onQueryChange={setQuery}
          onFiltersChange={updateFilters}
          onOpenScope={switchScope}
          onSubmit={submit}
        />
      </div>
      {active !== null && active.access_state !== "accessible" ? (
        <p className="mx-auto max-w-6xl px-6 pb-2 font-display text-xs italic text-claret">
          Access to {active.display_name} is restricted.
        </p>
      ) : null}
    </div>
  );
}
