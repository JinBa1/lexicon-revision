import { ActionPair } from "./ActionPair";
import { FiltersChip } from "./FiltersChip";
import { ScopeChip } from "./ScopeChip";
import type { CollectionListItem, FilterCondition } from "@/lib/api/types";

export function ScopeRow({
  activeCollection,
  filters,
  onFiltersChange,
  onOpenScope,
  onSubmit,
}: {
  activeCollection: CollectionListItem | null;
  filters: FilterCondition[];
  onFiltersChange: (next: FilterCondition[]) => void;
  onOpenScope: () => void;
  onSubmit: (action: "questions" | "answer") => void;
}) {
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-ui text-[10px] uppercase tracking-wider text-ink-muted">In</span>
        <ScopeChip collection={activeCollection} onOpen={onOpenScope} />
        <FiltersChip
          schema={activeCollection?.metadata_schema ?? null}
          value={filters}
          onChange={onFiltersChange}
        />
      </div>
      <ActionPair
        onFindQuestions={() => onSubmit("questions")}
        onGetAnswer={() => onSubmit("answer")}
      />
    </div>
  );
}
