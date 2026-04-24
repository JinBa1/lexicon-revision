import { useState } from "react";

import { SignUp } from "@clerk/react";
import { Route, Routes, useNavigate, useSearchParams } from "react-router-dom";

import { UniversityGate } from "@/components/auth/UniversityGate";
import { Button } from "@/components/shared/Button";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingSkeleton } from "@/components/shared/LoadingSkeleton";
import { env } from "@/env";
import { useAppAuth } from "@/lib/auth/runtime";
import { useSupportedUniversities } from "@/lib/hooks/useSupportedUniversities";

export function SignUpRoute() {
  return (
    <Routes>
      <Route index element={<SignUpGate />} />
      <Route path="create/*" element={<SignUpCreate />} />
    </Routes>
  );
}

function SignUpGate() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useSupportedUniversities();
  const returnTo = sanitizeAppPath(params.get("returnTo"));
  const requestedUniversity = params.get("university");

  if (isLoading) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-12">
        <LoadingSkeleton variant="card" count={4} />
      </main>
    );
  }

  if (isError || !data || data.length === 0) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-12">
        <ErrorState title="Couldn't load supported universities" />
      </main>
    );
  }

  const initialSelected = data.some((university) => university.id === requestedUniversity)
    ? requestedUniversity
    : null;

  return (
    <UniversityGate
      universities={data}
      initialSelected={initialSelected}
      onContinue={(universityId) => {
        const qs = new URLSearchParams({ university: universityId, returnTo });
        navigate(`/sign-up/create?${qs.toString()}`);
      }}
    />
  );
}

function SignUpCreate() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { authMode, stubHeaderEmail, setStubHeaderEmail } = useAppAuth();
  const universityId = params.get("university");
  const returnTo = sanitizeAppPath(params.get("returnTo"));
  const { data: universities } = useSupportedUniversities();
  const university = universities?.find((item) => item.id === universityId) ?? null;
  const [email, setEmail] = useState(stubHeaderEmail ?? env.stubAuthEmail ?? "");

  if (authMode === "stub_header") {
    return (
      <main className="mx-auto flex max-w-md flex-col px-6 py-12">
        <h1 className="font-display text-3xl font-semibold text-ink">Create account</h1>
        {university ? (
          <p className="mt-2 font-body text-ink-muted">
            Use an email for{" "}
            <span className="font-mono text-sm text-ink">@{university.email_domains[0]}</span> to
            match this university in local stub mode.
          </p>
        ) : null}
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
              placeholder={
                university ? `you@${university.email_domains[0]}` : "student@example.edu"
              }
            />
          </label>
          <Button type="submit" variant="primary">
            Continue
          </Button>
        </form>
      </main>
    );
  }

  const signInUrl = `/sign-in?${new URLSearchParams({ returnTo }).toString()}`;

  return (
    <main className="mx-auto flex max-w-md flex-col items-center px-6 py-12">
      {university ? (
        <p className="mb-4 font-body text-sm italic text-ink-muted">
          Use your{" "}
          <span className="font-mono not-italic text-ink">@{university.email_domains[0]}</span>{" "}
          email address.
        </p>
      ) : null}
      <SignUp
        routing="path"
        path="/sign-up/create"
        signInUrl={signInUrl}
        forceRedirectUrl={returnTo}
        appearance={{
          variables: {
            colorPrimary: "#7E2E2E",
            colorBackground: "#FBF6E8",
            colorText: "#211D1A",
            colorTextSecondary: "#6E625A",
            fontFamily: '"Source Serif Pro", Georgia, serif',
          },
          elements: {
            cardBox: "shadow-none border border-rule rounded-sm",
            headerTitle: "font-display",
            formButtonPrimary: "bg-claret hover:bg-claret/90",
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
