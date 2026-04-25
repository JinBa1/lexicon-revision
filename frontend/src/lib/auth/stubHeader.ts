import { useCallback, useMemo } from "react";

import { useNavigate } from "react-router-dom";

import { env } from "@/env";
import type { ApiClient } from "@/lib/api/client";
import { readStubHeaderEmail } from "@/lib/auth/runtime";

export function useStubHeaderApiClient(): ApiClient {
  const navigate = useNavigate();

  const getAuthHeaders = useCallback(async () => {
    const headers: Record<string, string> = {};
    const storedEmail = readStubHeaderEmail();
    const email = storedEmail === null ? env.stubAuthEmail : storedEmail;
    if (email) {
      headers["X-User-Email"] = email;
    }

    return headers;
  }, []);

  const onUnauthorized = useCallback(() => {
    const current = `${window.location.pathname}${window.location.search}`;
    navigate(`/sign-in?returnTo=${encodeURIComponent(current)}`);
  }, [navigate]);

  return useMemo(() => ({ getAuthHeaders, onUnauthorized }), [getAuthHeaders, onUnauthorized]);
}
