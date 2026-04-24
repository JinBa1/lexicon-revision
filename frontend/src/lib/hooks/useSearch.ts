import { useQuery } from "@tanstack/react-query";
import { fetchSearch } from "@/lib/api/search";
import { useApiClient } from "./useApiClient";
import type { FilterCondition } from "@/lib/api/types";

export function useSearch(params: {
  collection: string;
  query: string;
  filters: FilterCondition[];
  enabled: boolean;
}) {
  const client = useApiClient();
  return useQuery({
    queryKey: ["search", params.collection, params.query, params.filters],
    queryFn: () =>
      fetchSearch(client, {
        collection: params.collection,
        query: params.query,
        filters: params.filters,
        limit: 15,
        rerank: true,
      }),
    enabled: params.enabled,
    staleTime: 2 * 60_000,
  });
}
