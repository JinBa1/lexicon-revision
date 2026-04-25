import { env } from "@/env";
import { useClerkApiClient } from "@/lib/auth/clerk";
import { useStubHeaderApiClient } from "@/lib/auth/stubHeader";

const useApiClientImpl = env.authMode === "clerk" ? useClerkApiClient : useStubHeaderApiClient;

export function useApiClient() {
  return useApiClientImpl();
}
