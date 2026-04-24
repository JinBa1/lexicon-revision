/* eslint-disable react-refresh/only-export-components */
import type { PropsWithChildren } from "react";

import { getClerkTestState } from "./clerk-state";

export { resetClerkTestState, setClerkTestState } from "./clerk-state";

export function ClerkProvider({ children }: PropsWithChildren) {
  return <>{children}</>;
}

export function ClerkLoaded({ children }: PropsWithChildren) {
  return <>{children}</>;
}

export function SignedIn({ children }: PropsWithChildren) {
  return getClerkTestState().isSignedIn ? <>{children}</> : null;
}

export function SignedOut({ children }: PropsWithChildren) {
  return getClerkTestState().isSignedIn ? null : <>{children}</>;
}

export function UserButton() {
  return <button type="button">User</button>;
}

export function SignIn(props: { fallbackRedirectUrl?: string }) {
  return (
    <div data-testid="clerk-sign-in">{props.fallbackRedirectUrl ?? "/"}</div>
  );
}

export function SignUp(props: {
  fallbackRedirectUrl?: string;
  forceRedirectUrl?: string;
}) {
  return (
    <div data-testid="clerk-sign-up">
      {props.forceRedirectUrl ?? props.fallbackRedirectUrl ?? "/"}
    </div>
  );
}

export function useAuth() {
  return {
    isLoaded: getClerkTestState().isLoaded,
    isSignedIn: getClerkTestState().isSignedIn,
    getToken: async () => getClerkTestState().token,
  };
}
