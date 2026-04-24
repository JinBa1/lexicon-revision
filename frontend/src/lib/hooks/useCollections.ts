import { useQuery } from "@tanstack/react-query";
import { fetchCollections } from "@/lib/api/collections";
import { useApiClient } from "./useApiClient";

export function useCollections() {
  const client = useApiClient();
  return useQuery({
    queryKey: ["collections"],
    queryFn: () => fetchCollections(client),
    staleTime: 5 * 60_000,
  });
}
