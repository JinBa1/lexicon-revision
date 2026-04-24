import { useQuery } from "@tanstack/react-query";
import { fetchChunk } from "@/lib/api/chunks";
import { useApiClient } from "./useApiClient";

export function useChunk(params: { collection: string; chunkId: string } | null) {
  const client = useApiClient();
  return useQuery({
    queryKey: ["chunk", params?.collection, params?.chunkId],
    queryFn: () => fetchChunk(client, params!),
    enabled: params !== null,
    staleTime: 10 * 60_000,
  });
}
