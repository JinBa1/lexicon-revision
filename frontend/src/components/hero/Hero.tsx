import { useCallback, type KeyboardEvent } from "react";

import { cn } from "@/lib/cn";
import type { CollectionListItem, FilterCondition } from "@/lib/api/types";

import { HelperExamples, type HelperExample } from "./HelperExamples";
import { QueryInput } from "./QueryInput";
import { ScopeRequiredHelper } from "./ScopeRequiredHelper";
import { ScopeRow } from "./ScopeRow";

export type HeroSubmitAction = "questions" | "answer";

export type HeroProps = {
  mode: "landing" | "header-echo";
  chrome?: "default" | "landing-unified";
  activeCollection: CollectionListItem | null;
  query: string;
  filters: FilterCondition[];
  onQueryChange: (next: string) => void;
  onFiltersChange: (next: FilterCondition[]) => void;
  onOpenScope: () => void;
  onSubmit: (action: HeroSubmitAction) => void;
  onScopeMissing?: () => void;
  showScopeRequiredHelper?: boolean;
};

export function Hero(props: HeroProps) {
  const {
    mode,
    chrome = "default",
    activeCollection,
    query,
    filters,
    onQueryChange,
    onFiltersChange,
    onOpenScope,
    onSubmit,
    onScopeMissing,
    showScopeRequiredHelper = true,
  } = props;

  const attemptSubmit = useCallback(
    (action: HeroSubmitAction) => {
      if (activeCollection === null) {
        onScopeMissing?.();
        return;
      }
      onSubmit(action);
    },
    [activeCollection, onScopeMissing, onSubmit],
  );

  const onInputKeyDown = useCallback(
    (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "Enter") {
        event.preventDefault();
        attemptSubmit("questions");
      }
    },
    [attemptSubmit],
  );

  const onHelperPick = useCallback(
    (example: HelperExample) => {
      onQueryChange(example.label);
      if (activeCollection === null) {
        onScopeMissing?.();
        return;
      }
      onSubmit(example.action);
    },
    [activeCollection, onQueryChange, onScopeMissing, onSubmit],
  );

  const isLandingUnified = chrome === "landing-unified";

  const queryInput = (
    <QueryInput
      size={mode === "landing" ? "lg" : "md"}
      chrome={isLandingUnified ? "landing-unified" : "default"}
      value={query}
      onChange={(event) => onQueryChange(event.currentTarget.value)}
      onKeyDown={onInputKeyDown}
    />
  );

  const scopeRow = (
    <ScopeRow
      activeCollection={activeCollection}
      filters={filters}
      onFiltersChange={onFiltersChange}
      onOpenScope={onOpenScope}
      onSubmit={attemptSubmit}
      chrome={isLandingUnified ? "landing-unified" : "default"}
    />
  );

  const landingHelper =
    mode === "landing" ? (
      <div
        className={cn(
          "font-body text-sm",
          isLandingUnified ? "space-y-3" : "mt-3 border-t border-rule-soft pt-3",
        )}
      >
        {activeCollection === null && showScopeRequiredHelper ? (
          <ScopeRequiredHelper />
        ) : activeCollection && !isLandingUnified ? (
          <div className="font-ui text-[11px] uppercase tracking-wider text-ink-muted">
            {describeMeta(activeCollection)}
          </div>
        ) : null}
        <HelperExamples
          onPick={onHelperPick}
          chrome={isLandingUnified ? "landing-unified" : "default"}
        />
      </div>
    ) : null;

  return (
    <section
      className={cn(
        isLandingUnified
          ? "flex flex-col gap-5 px-5 py-6 sm:px-9 sm:py-8"
          : "rounded-md border border-rule bg-paper-raised",
        !isLandingUnified && (mode === "landing" ? "p-5" : "p-3"),
      )}
    >
      {isLandingUnified ? (
        <>
          {scopeRow}
          {queryInput}
          {landingHelper}
        </>
      ) : (
        <>
          {queryInput}
          {scopeRow}
          {landingHelper}
        </>
      )}
    </section>
  );
}

function describeMeta(collection: CollectionListItem): string {
  const count = `${collection.paper_count} papers`;
  if (collection.year_range) {
    return `${count} · ${collection.year_range.start}–${collection.year_range.end}`;
  }
  return count;
}
