import type { CollectionListItem } from "./types";
import { apiFetch } from "./fetcher";
import type { ApiClient } from "./client";

export async function fetchCollections(client: ApiClient): Promise<CollectionListItem[]> {
  return apiFetch<CollectionListItem[]>({
    path: "/collections",
    getAuthHeaders: client.getAuthHeaders,
    onUnauthorized: client.onUnauthorized,
  });
}
