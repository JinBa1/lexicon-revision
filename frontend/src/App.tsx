import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { Footer } from "@/components/nav/Footer";
import { TopNav } from "@/components/nav/TopNav";
import { AppAuthProvider } from "@/lib/auth/runtime";
import { AboutRoute } from "@/routes/about";
import { AnswerRoute } from "@/routes/answer";
import { CollectionHomeRoute } from "@/routes/collection-home";
import { LandingRoute } from "@/routes/landing";
import { NotFoundRoute } from "@/routes/not-found";
import { PrivacyRoute } from "@/routes/privacy";
import { QuestionsRoute } from "@/routes/questions";
import { SignInRoute } from "@/routes/sign-in";
import { SignUpRoute } from "@/routes/sign-up";
import { SourceRoute } from "@/routes/source";
import { UnlockRoute } from "@/routes/unlock";
import { isRateLimitBackoffError } from "@/lib/api/errors";

// eslint-disable-next-line react-refresh/only-export-components
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (isRateLimitBackoffError(error)) {
    return false;
  }

  const status = (error as { status?: number } | null)?.status ?? 0;
  if (status === 401 || status === 403 || status === 404 || status === 422) {
    return false;
  }

  return failureCount < 1;
}

type QueryWithError = {
  state: {
    error: unknown;
  };
};

// eslint-disable-next-line react-refresh/only-export-components
export function shouldAutoRefetchQuery(query: QueryWithError): boolean {
  return !isRateLimitBackoffError(query.state.error);
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: shouldAutoRefetchQuery,
      refetchOnReconnect: shouldAutoRefetchQuery,
      refetchOnMount: shouldAutoRefetchQuery,
      staleTime: 60_000,
      retry: shouldRetryQuery,
    },
  },
});

export function App() {
  return (
    <AppAuthProvider>
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          <div className="flex min-h-screen flex-col bg-paper">
            <TopNav />
            <div className="flex-1">
              <Routes>
                <Route path="/" element={<LandingRoute />} />
                <Route path="/c/:collection" element={<CollectionHomeRoute />} />
                <Route path="/c/:collection/questions" element={<QuestionsRoute />} />
                <Route path="/c/:collection/answer" element={<AnswerRoute />} />
                <Route path="/c/:collection/source/:chunkId" element={<SourceRoute />} />
                <Route path="/unlock/:collection" element={<UnlockRoute />} />
                <Route path="/sign-in/*" element={<SignInRoute />} />
                <Route path="/sign-up/*" element={<SignUpRoute />} />
                <Route path="/about" element={<AboutRoute />} />
                <Route path="/privacy" element={<PrivacyRoute />} />
                <Route path="*" element={<NotFoundRoute />} />
              </Routes>
            </div>
            <Footer />
          </div>
        </QueryClientProvider>
      </BrowserRouter>
    </AppAuthProvider>
  );
}
