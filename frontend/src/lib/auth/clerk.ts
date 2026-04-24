import { useCallback, useMemo } from "react";

import { useAuth } from "@clerk/react";
import { useNavigate } from "react-router-dom";

import type { ApiClient } from "@/lib/api/client";

export function useClerkApiClient(): ApiClient {
  const { getToken } = useAuth();
  const navigate = useNavigate();

  const getAuthHeaders = useCallback(async () => {
    const headers: Record<string, string> = {};

    try {
      const token = (await getToken()) ?? null;
      if (token) {
        headers.authorization = `Bearer ${token}`;
      }
    } catch {
      return headers;
    }

    return headers;
  }, [getToken]);

  const onUnauthorized = useCallback(() => {
    const current = `${window.location.pathname}${window.location.search}`;
    navigate(`/sign-in?returnTo=${encodeURIComponent(current)}`);
  }, [navigate]);

  return useMemo(
    () => ({ getAuthHeaders, onUnauthorized }),
    [getAuthHeaders, onUnauthorized],
  );
}
