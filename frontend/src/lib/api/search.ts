import type { SearchRequest, SearchResponse } from "./types";
import { apiFetch } from "./fetcher";
import type { ApiClient } from "./client";

export async function fetchSearch(
  client: ApiClient,
  request: SearchRequest,
): Promise<SearchResponse> {
  return apiFetch<SearchResponse>({
    path: "/search",
    method: "POST",
    body: request,
    getAuthHeaders: client.getAuthHeaders,
    onUnauthorized: client.onUnauthorized,
  });
}
