import { Link } from "react-router-dom";

export function Footer() {
  return (
    <footer className="mt-16 border-t border-rule bg-paper-sunken">
      <div className="mx-auto flex max-w-6xl justify-center px-6 py-6 font-ui text-[11px] uppercase tracking-[0.14em] text-ink-muted">
        <nav aria-label="Footer" className="flex flex-wrap justify-center gap-4">
          <Link to="/sign-up">Supported universities</Link>
          <Link to="/about">About</Link>
          <Link to="/privacy">Privacy</Link>
        </nav>
      </div>
    </footer>
  );
}
