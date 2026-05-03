import { Link } from "react-router-dom";

import { AppUserButton, useAppAuth } from "@/lib/auth/runtime";
import { PRODUCT_NAME } from "@/lib/publicCopy";

export function TopNav() {
  const { isSignedIn } = useAppAuth();

  return (
    <header className="sticky top-0 z-20 border-b border-rule-soft bg-paper-raised">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link
          to="/"
          className="font-display text-[12px] font-bold uppercase tracking-[0.18em] text-ink transition-colors hover:text-claret sm:text-[15px]"
        >
          {PRODUCT_NAME}
        </Link>
        <nav aria-label="Primary" className="flex items-center gap-5 font-ui">
          <Link
            to="/sign-up"
            className="hidden text-[11px] font-medium uppercase tracking-wider text-ink-muted transition-colors hover:text-claret md:inline"
          >
            Supported universities
          </Link>
          <Link
            to="/about"
            className="hidden text-[11px] font-medium uppercase tracking-wider text-ink-muted transition-colors hover:text-claret md:inline"
          >
            About
          </Link>
          {!isSignedIn ? (
            <Link
              to="/sign-in"
              className="inline-flex items-center gap-2 rounded-md border border-claret bg-white px-4 py-1.5 text-[11px] font-bold uppercase tracking-[0.12em] text-claret transition-colors hover:bg-claret-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
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
