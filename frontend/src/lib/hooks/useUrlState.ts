import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { parseFiltersFromSearchParams, type ParseResult } from "@/lib/url/filters";
import { parseQueryFromSearchParams } from "@/lib/url/scope";
import type { CollectionMetadataSchema } from "@/lib/api/types";

export type UrlState = {
  query: string;
  filterParse: ParseResult;
};

export function useUrlState(schema: CollectionMetadataSchema | null): UrlState {
  const [searchParams] = useSearchParams();

  return useMemo(
    () => ({
      query: parseQueryFromSearchParams(searchParams),
      filterParse: parseFiltersFromSearchParams(searchParams, schema),
    }),
    [searchParams, schema],
  );
}
