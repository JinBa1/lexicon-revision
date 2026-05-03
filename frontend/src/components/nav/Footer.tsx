import { Link } from "react-router-dom";

import { env } from "@/env";
import { PRODUCT_NAME } from "@/lib/publicCopy";

export function Footer() {
  return (
    <footer className="mt-16 border-t border-rule bg-paper-sunken">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-4 px-6 py-6 font-ui text-[11px] uppercase tracking-[0.14em] text-ink-muted">
        <div className="flex flex-col gap-1">
          <span className="font-semibold tracking-[0.18em] text-ink">{PRODUCT_NAME}</span>
          <span className="font-display italic normal-case tracking-normal">
            Read the question. Then ask yours.
          </span>
        </div>
        <nav aria-label="Footer" className="flex flex-wrap gap-4">
          <Link to="/sign-up">Supported universities</Link>
          <Link to="/about">About</Link>
          <Link to="/privacy">Privacy</Link>
        </nav>
        <span>
          Est. 2026 · <span className="font-mono text-[10px]">{env.buildSha.slice(0, 7)}</span>
        </span>
      </div>
    </footer>
  );
}
