import type { StudyRequest, StudyResponse } from "./types";
import { apiFetch } from "./fetcher";
import type { ApiClient } from "./client";

export async function fetchStudy(client: ApiClient, request: StudyRequest): Promise<StudyResponse> {
  return apiFetch<StudyResponse>({
    path: "/study",
    method: "POST",
    body: request,
    getAuthHeaders: client.getAuthHeaders,
    onUnauthorized: client.onUnauthorized,
  });
}
