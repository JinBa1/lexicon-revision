import type { SupportedUniversity } from "./types";
import { apiFetch } from "./fetcher";
import type { ApiClient } from "./client";

export async function fetchSupportedUniversities(
  client: ApiClient,
): Promise<SupportedUniversity[]> {
  return apiFetch<SupportedUniversity[]>({
    path: "/supported-universities",
    getAuthHeaders: client.getAuthHeaders,
    onUnauthorized: client.onUnauthorized,
  });
}
