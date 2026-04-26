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

  return (
    <section
      className={cn(
        "rounded-md border border-rule bg-paper-raised",
        mode === "landing" ? "p-5" : "p-3",
      )}
    >
      <QueryInput
        size={mode === "landing" ? "lg" : "md"}
        value={query}
        onChange={(event) => onQueryChange(event.currentTarget.value)}
        onKeyDown={onInputKeyDown}
      />
      <ScopeRow
        activeCollection={activeCollection}
        filters={filters}
        onFiltersChange={onFiltersChange}
        onOpenScope={onOpenScope}
        onSubmit={attemptSubmit}
      />
      {mode === "landing" ? (
        <div className="mt-3 border-t border-rule-soft pt-3 font-body text-sm">
          {activeCollection === null && showScopeRequiredHelper ? (
            <ScopeRequiredHelper />
          ) : activeCollection ? (
            <div className="font-ui text-[11px] uppercase tracking-wider text-ink-muted">
              {describeMeta(activeCollection)}
            </div>
          ) : null}
          <HelperExamples onPick={onHelperPick} />
        </div>
      ) : null}
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
