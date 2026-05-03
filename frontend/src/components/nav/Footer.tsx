import { Link } from "react-router-dom";

import { env } from "@/env";

export function Footer() {
  return (
    <footer className="mx-auto mt-16 flex max-w-6xl flex-wrap items-center justify-between gap-4 border-t border-rule px-6 py-6 font-display text-[11px] uppercase tracking-[0.14em] text-ink-muted">
      <span className="italic normal-case tracking-normal">Read the question. Then ask yours.</span>
      <nav aria-label="Footer" className="flex flex-wrap gap-4">
        <Link to="/sign-up">Supported universities</Link>
        <Link to="/about">About</Link>
        <Link to="/privacy">Privacy</Link>
      </nav>
      <span>
        Est. 2026 · <span className="font-mono text-[10px]">{env.buildSha.slice(0, 7)}</span>
      </span>
    </footer>
  );
}
