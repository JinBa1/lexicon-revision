import { useQuery } from "@tanstack/react-query";
import { fetchStudy } from "@/lib/api/study";
import { useApiClient } from "./useApiClient";
import type { FilterCondition } from "@/lib/api/types";

export function useStudy(params: {
  collection: string;
  query: string;
  filters: FilterCondition[];
  enabled: boolean;
}) {
  const client = useApiClient();
  return useQuery({
    queryKey: ["study", params.collection, params.query, params.filters],
    queryFn: () =>
      fetchStudy(client, {
        query: params.query,
        scope: { collection: params.collection },
        filters: params.filters,
        top_k: 15,
      }),
    enabled: params.enabled,
    staleTime: 5 * 60_000,
  });
}
