/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import { ClerkProvider, UserButton, useAuth } from "@clerk/react";

import { env } from "@/env";

type AuthMode = "stub_header" | "clerk";

type AppAuthValue = {
  authMode: AuthMode;
  isSignedIn: boolean;
  stubHeaderEmail: string | null;
  setStubHeaderEmail: (email: string | null) => void;
};

const STUB_HEADER_STORAGE_KEY = "rag_exam.stub_header_email";

const AppAuthContext = createContext<AppAuthValue | null>(null);

export function readStubHeaderEmail(): string | null {
  const storage = getSessionStorage();
  if (!storage) return null;

  const storedValue = storage.getItem(STUB_HEADER_STORAGE_KEY);
  if (storedValue === null) return null;

  return storedValue.trim();
}

export function AppAuthProvider({ children }: PropsWithChildren) {
  if (env.authMode === "clerk") {
    return (
      <ClerkProvider publishableKey={env.clerkPublishableKey}>
        <ClerkAppAuthProvider>{children}</ClerkAppAuthProvider>
      </ClerkProvider>
    );
  }

  return <StubHeaderAppAuthProvider>{children}</StubHeaderAppAuthProvider>;
}

export function useAppAuth(): AppAuthValue {
  const value = useContext(AppAuthContext);
  if (!value) {
    throw new Error("useAppAuth must be used within AppAuthProvider");
  }

  return value;
}

export function AppUserButton() {
  const { authMode, stubHeaderEmail, setStubHeaderEmail } = useAppAuth();

  if (authMode === "clerk") {
    return <UserButton />;
  }

  if (!stubHeaderEmail) {
    return null;
  }

  return (
    <button
      type="button"
      className="rounded-md border border-rule px-3 py-2 font-ui text-xs uppercase tracking-[0.2em] text-ink"
      onClick={() => setStubHeaderEmail(null)}
    >
      {stubHeaderEmail} · Sign out
    </button>
  );
}

function ClerkAppAuthProvider({ children }: PropsWithChildren) {
  const { isSignedIn } = useAuth();
  const setStubHeaderEmail = useCallback(() => {}, []);

  const value = useMemo<AppAuthValue>(
    () => ({
      authMode: "clerk",
      isSignedIn: Boolean(isSignedIn),
      stubHeaderEmail: null,
      setStubHeaderEmail,
    }),
    [isSignedIn, setStubHeaderEmail],
  );

  return <AppAuthContext.Provider value={value}>{children}</AppAuthContext.Provider>;
}

function StubHeaderAppAuthProvider({ children }: PropsWithChildren) {
  const [stubHeaderEmail, setStubHeaderEmailState] = useState<string | null>(() =>
    normalizeStubHeaderEmail(readStubHeaderEmail() ?? env.stubAuthEmail),
  );

  useEffect(() => {
    writeStubHeaderEmail(stubHeaderEmail);
  }, [stubHeaderEmail]);

  const setStubHeaderEmail = useCallback((email: string | null) => {
    const nextEmail = normalizeStubHeaderEmail(email);
    writeStubHeaderEmail(nextEmail);
    setStubHeaderEmailState(nextEmail);
  }, []);

  const value = useMemo<AppAuthValue>(
    () => ({
      authMode: "stub_header",
      isSignedIn: Boolean(stubHeaderEmail),
      stubHeaderEmail,
      setStubHeaderEmail,
    }),
    [stubHeaderEmail, setStubHeaderEmail],
  );

  return <AppAuthContext.Provider value={value}>{children}</AppAuthContext.Provider>;
}

function normalizeStubHeaderEmail(email: string | null): string | null {
  if (email === null) {
    return null;
  }

  const trimmed = email.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function writeStubHeaderEmail(email: string | null): void {
  const storage = getSessionStorage();
  if (!storage) return;

  storage.setItem(STUB_HEADER_STORAGE_KEY, email ?? "");
}

function getSessionStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}
