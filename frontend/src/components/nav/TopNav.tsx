import { Link } from "react-router-dom";

import { AppUserButton, useAppAuth } from "@/lib/auth/runtime";

export function TopNav() {
  const { isSignedIn } = useAppAuth();

  return (
    <header className="sticky top-0 z-20 border-b border-rule bg-paper-sunken">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link
          to="/"
          className="font-display text-[13px] font-bold uppercase tracking-[0.22em] text-ink"
        >
          The Tripos Archive
        </Link>
        <nav className="flex items-center gap-5">
          <Link
            to="/sign-up"
            className="hidden font-ui text-[11px] uppercase tracking-wider text-ink-muted md:inline"
          >
            Supported universities
          </Link>
          <Link
            to="/about"
            className="hidden font-ui text-[11px] uppercase tracking-wider text-ink-muted md:inline"
          >
            About
          </Link>
          {!isSignedIn ? (
            <Link
              to="/sign-in"
              className="inline-flex items-center gap-2 rounded-md border border-claret bg-transparent px-4 py-1.5 font-display text-[11px] uppercase tracking-wider text-claret transition-colors hover:bg-claret/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
            >
              Sign in
            </Link>
          ) : (
            <AppUserButton />
          )}
        </nav>
      </div>
    </header>
  );
}
