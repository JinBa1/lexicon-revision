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
import { QuestionsRoute } from "@/routes/questions";
import { SignInRoute } from "@/routes/sign-in";
import { SignUpRoute } from "@/routes/sign-up";
import { SourceRoute } from "@/routes/source";
import { UnlockRoute } from "@/routes/unlock";

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
