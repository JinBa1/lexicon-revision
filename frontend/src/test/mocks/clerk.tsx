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

export function SignIn(props: {
  routing?: string;
  path?: string;
  signUpUrl?: string;
  fallbackRedirectUrl?: string;
  signUpFallbackRedirectUrl?: string;
}) {
  return (
    <div
      data-testid="clerk-sign-in"
      data-routing={props.routing}
      data-path={props.path}
      data-sign-up-url={props.signUpUrl}
      data-fallback-redirect-url={props.fallbackRedirectUrl}
      data-sign-up-fallback-redirect-url={props.signUpFallbackRedirectUrl}
    >
      {props.fallbackRedirectUrl ?? "/"}
    </div>
  );
}

export function SignUp(props: { fallbackRedirectUrl?: string; forceRedirectUrl?: string }) {
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
