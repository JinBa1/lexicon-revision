import { useQuery } from "@tanstack/react-query";
import { fetchSupportedUniversities } from "@/lib/api/supportedUniversities";
import { useApiClient } from "./useApiClient";

export function useSupportedUniversities() {
  const client = useApiClient();
  return useQuery({
    queryKey: ["supported-universities"],
    queryFn: () => fetchSupportedUniversities(client),
    staleTime: 60 * 60_000,
  });
}
