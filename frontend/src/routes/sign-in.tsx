import { useState } from "react";

import { SignIn } from "@clerk/react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Button } from "@/components/shared/Button";
import { env } from "@/env";
import { useAppAuth } from "@/lib/auth/runtime";

export function SignInRoute() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { authMode, stubHeaderEmail, setStubHeaderEmail } = useAppAuth();
  const returnTo = sanitizeAppPath(params.get("returnTo"));
  const [email, setEmail] = useState(stubHeaderEmail ?? env.stubAuthEmail ?? "");

  if (authMode === "stub_header") {
    return (
      <main className="mx-auto flex max-w-md flex-col px-6 py-12">
        <h1 className="font-display text-3xl font-semibold text-ink">Sign in</h1>
        <p className="mt-2 font-body text-ink-muted">
          Local stub auth mode. Enter an email to send as X-User-Email; the backend decides whether
          that identity is accessible, locked, or wrong-affiliation after redirect.
        </p>
        <form
          className="mt-6 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            setStubHeaderEmail(email.trim());
            navigate(returnTo, { replace: true });
          }}
        >
          <label className="block font-ui text-xs uppercase tracking-[0.2em] text-ink-muted">
            Email
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.currentTarget.value)}
              className="mt-2 w-full rounded-sm border border-rule bg-white px-3 py-2 font-body text-base normal-case tracking-normal text-ink"
              placeholder="student@example.edu"
            />
          </label>
          <Button type="submit" variant="primary">
            Continue
          </Button>
        </form>
      </main>
    );
  }

  return (
    <main className="mx-auto flex max-w-md flex-col items-center px-6 py-12">
      <SignIn
        routing="path"
        path="/sign-in"
        signUpUrl={`/sign-up?${new URLSearchParams({ returnTo }).toString()}`}
        fallbackRedirectUrl={returnTo}
        signUpFallbackRedirectUrl={returnTo}
        appearance={{
          variables: {
            colorPrimary: "#7E2E2E",
            colorBackground: "#FBF6E8",
            fontFamily: '"Source Serif Pro", Georgia, serif',
          },
        }}
      />
    </main>
  );
}

function sanitizeAppPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) {
    return "/";
  }

  return value;
}
