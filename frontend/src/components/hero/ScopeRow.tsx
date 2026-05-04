import { ActionPair } from "./ActionPair";
import { FiltersChip } from "./FiltersChip";
import { ScopeChip } from "./ScopeChip";
import type { CollectionListItem, FilterCondition } from "@/lib/api/types";
import { cn } from "@/lib/cn";

export function ScopeRow({
  activeCollection,
  filters,
  onFiltersChange,
  onOpenScope,
  onSubmit,
  chrome = "default",
}: {
  activeCollection: CollectionListItem | null;
  filters: FilterCondition[];
  onFiltersChange: (next: FilterCondition[]) => void;
  onOpenScope: () => void;
  onSubmit: (action: "questions" | "answer") => void;
  chrome?: "default" | "landing-unified" | "result-unified";
}) {
  if (chrome === "landing-unified" || chrome === "result-unified") {
    const isResultUnified = chrome === "result-unified";
    const scopeLabel = activeCollection ? activeCollection.display_name : "Pick a collection";

    return (
      <div
        data-testid="hero-action-row"
        className="flex flex-col justify-between gap-3 lg:flex-row lg:items-stretch lg:justify-between"
      >
        <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-stretch">
          <button
            type="button"
            onClick={onOpenScope}
            aria-label={scopeLabel}
            className={cn(
              "flex min-h-14 w-full min-w-0 items-center gap-3 rounded border border-rule bg-[#FDFBF5] px-4 py-3 text-left transition-colors hover:border-ink-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 focus-visible:ring-offset-paper",
              isResultUnified ? "md:w-[360px]" : "md:w-[380px]",
            )}
          >
            <span aria-hidden className="text-lg text-ink-muted">
              🏛
            </span>
            <span className="min-w-0">
              <span className="block font-ui text-[9px] font-bold uppercase tracking-[0.14em] text-ink-muted">
                Current Collection
              </span>
              <span className="mt-1 block truncate font-display text-[17px] font-semibold leading-tight text-ink">
                {scopeLabel}
              </span>
            </span>
          </button>

          {activeCollection !== null ? (
            <FiltersChip
              schema={activeCollection.metadata_schema}
              value={filters}
              onChange={onFiltersChange}
              chrome={chrome}
            />
          ) : null}
        </div>

        <div className="lg:ml-6 lg:shrink-0">
          <ActionPair
            onFindQuestions={() => onSubmit("questions")}
            onGetAnswer={() => onSubmit("answer")}
            chrome={chrome}
          />
        </div>
      </div>
    );
  }

  return (
    <div className={cn("mt-3 flex flex-wrap items-center justify-between gap-3")}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-ui text-[10px] uppercase tracking-wider text-ink-muted">In</span>
        <ScopeChip collection={activeCollection} onOpen={onOpenScope} />
        {activeCollection !== null ? (
          <FiltersChip
            schema={activeCollection.metadata_schema}
            value={filters}
            onChange={onFiltersChange}
          />
        ) : null}
      </div>
      <ActionPair
        onFindQuestions={() => onSubmit("questions")}
        onGetAnswer={() => onSubmit("answer")}
      />
    </div>
  );
}
