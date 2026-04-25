import { useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "@/components/shared/Button";
import { ErrorState } from "@/components/shared/ErrorState";
import { buildCollectionHref } from "@/lib/url/scope";

export function InvalidFiltersState({
  collectionName,
  offendingField,
}: {
  collectionName: string;
  offendingField?: string;
}) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  return (
    <div className="p-10">
      <ErrorState
        title="Filters in this link aren't valid"
        detail={
          offendingField
            ? `The filter "${offendingField}" is not available in ${collectionName}. Adjust or clear filters to continue.`
            : "Adjust or clear filters to continue."
        }
        actions={
          <>
            <Button
              variant="primary"
              onClick={() => {
                const next = new URLSearchParams(searchParams);
                next.delete("filter");
                setSearchParams(next);
              }}
            >
              Clear filters
            </Button>
            <Button
              variant="secondary"
              onClick={() => navigate(buildCollectionHref(collectionName))}
            >
              Back to collection
            </Button>
          </>
        }
      />
    </div>
  );
}
