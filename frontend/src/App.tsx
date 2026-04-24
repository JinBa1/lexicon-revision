import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppAuthProvider } from "@/lib/auth/runtime";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      staleTime: 60_000,
      retry: (failureCount, error: unknown) => {
        const status = (error as { status?: number } | null)?.status ?? 0;
        if (status === 401 || status === 403 || status === 404 || status === 422) {
          return false;
        }

        return failureCount < 1;
      },
    },
  },
});

export function App() {
  return (
    <AppAuthProvider>
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <Routes>
            <Route path="/" element={<PlaceholderLanding />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </QueryClientProvider>
      </BrowserRouter>
    </AppAuthProvider>
  );
}

function PlaceholderLanding() {
  return (
    <main className="min-h-screen bg-paper p-8 font-display text-ink">
      Providers wired. Routes pending.
    </main>
  );
}
