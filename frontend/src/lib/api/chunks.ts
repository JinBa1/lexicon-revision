import type { ChunkDetail } from "./types";
import { apiFetch } from "./fetcher";
import type { ApiClient } from "./client";

export async function fetchChunk(
  client: ApiClient,
  params: { collection: string; chunkId: string },
): Promise<ChunkDetail> {
  return apiFetch<ChunkDetail>({
    path: `/collections/${encodeURIComponent(params.collection)}/chunks/${encodeURIComponent(params.chunkId)}`,
    getAuthHeaders: client.getAuthHeaders,
    onUnauthorized: client.onUnauthorized,
  });
}
