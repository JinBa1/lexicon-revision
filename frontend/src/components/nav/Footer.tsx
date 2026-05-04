import { MarkGithubIcon } from "@primer/octicons-react";
import { Link } from "react-router-dom";

import { PRODUCT_NAME, PROJECT_REPOSITORY_URL } from "@/lib/publicCopy";

export function Footer() {
  return (
    <footer className="mt-16 border-t border-rule bg-paper-footer py-5 sm:py-6">
      <div className="mx-auto max-w-6xl px-6 font-ui text-[11px] uppercase tracking-[0.18em] text-ink-muted">
        <nav
          aria-label="Footer"
          className="grid grid-cols-1 items-center gap-3 font-bold sm:grid-cols-[1fr_auto_1fr]"
        >
          <div className="flex justify-center sm:justify-end">
            <Link to="/sign-up">Supported universities</Link>
          </div>
          <a
            href={PROJECT_REPOSITORY_URL}
            target="_blank"
            rel="noreferrer"
            aria-label="Project repository on GitHub"
            title="GitHub repository"
            className="mx-auto inline-flex items-center justify-center rounded-sm border border-transparent p-1 text-ink-muted transition-colors hover:text-claret focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 focus-visible:ring-offset-paper-footer"
          >
            <MarkGithubIcon size={28} aria-hidden="true" />
          </a>
          <div className="flex justify-center gap-8 sm:justify-start">
            <Link to="/about">About</Link>
            <Link to="/privacy">Privacy</Link>
          </div>
        </nav>
        <div className="mt-4 text-center tracking-[0.2em]">© 2026 {PRODUCT_NAME}</div>
      </div>
    </footer>
  );
}
