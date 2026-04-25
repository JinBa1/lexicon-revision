import type { GetAuthHeaders } from "./fetcher";

export type ApiClient = {
  getAuthHeaders: GetAuthHeaders;
  onUnauthorized: () => void;
};
