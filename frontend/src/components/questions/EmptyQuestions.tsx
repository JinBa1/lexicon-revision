import { Link } from "react-router-dom";

import { Button } from "@/components/shared/Button";
import { EmptyState } from "@/components/shared/EmptyState";
import type { FilterCondition } from "@/lib/api/types";
import { buildAnswerHref } from "@/lib/url/scope";

export function EmptyQuestions({
  collectionName,
  collectionDisplay,
  query,
  filters,
  onEditFilters,
  onSwitchCollection,
}: {
  collectionName: string;
  collectionDisplay: string;
  query: string;
  filters: FilterCondition[];
  onEditFilters: () => void;
  onSwitchCollection: () => void;
}) {
  return (
    <EmptyState
      title={`No past-paper questions match this query in ${collectionDisplay}`}
      detail="Try fewer filters, another collection, or ask for a grounded answer over the same scope."
      actions={
        <>
          <Button variant="secondary" onClick={onEditFilters}>
            Broaden filters
          </Button>
          <Button variant="secondary" onClick={onSwitchCollection}>
            Switch collection
          </Button>
          <Link
            to={buildAnswerHref({
              collection: collectionName,
              query,
              filters,
            })}
            className="inline-flex items-center gap-2 rounded-md border border-claret bg-claret px-4 py-2 font-display text-sm font-semibold text-paper-raised transition-colors hover:bg-claret/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
          >
            Try a grounded answer instead
          </Link>
        </>
      }
    />
  );
}
