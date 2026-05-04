import type { ReactNode } from "react";
import { Link } from "react-router-dom";

type MetaItem = {
  label: string;
  value: string;
};

type DocumentPageProps = {
  title: string;
  lead: string;
  meta: MetaItem[];
  children: ReactNode;
};

export function DocumentPage({ title, lead, meta, children }: DocumentPageProps) {
  return (
    <main className="mx-auto max-w-[760px] px-6 py-12 pb-20 text-ink sm:px-8">
      <Link to="/" className="font-ui text-[12.5px] font-semibold text-claret hover:underline">
        ← Back to home
      </Link>
      <h1 className="mt-7 font-display text-[38px] font-bold leading-[1.15] text-ink sm:text-[42px]">
        {title}
      </h1>
      <p className="mt-5 max-w-[60ch] font-display text-[17px] leading-[1.65] text-ink-muted">
        {lead}
      </p>
      <div className="mt-7 flex flex-wrap gap-4 border-b border-rule pb-5 font-ui text-[11.5px] text-ink-muted">
        {meta.map((item) => (
          <span key={item.label} className="inline-flex gap-1">
            <span>{item.label}</span>
            <strong className="font-semibold text-ink">{item.value}</strong>
          </span>
        ))}
      </div>
      <div
        data-testid="doc-content-panel"
        className="mt-8 rounded-[4px] border border-rule bg-paper-raised px-6 py-7 shadow-[0_12px_35px_rgba(0,0,0,0.04)] sm:px-9 sm:py-8"
      >
        {children}
      </div>
    </main>
  );
}

export function DocumentSection({
  index,
  title,
  children,
}: {
  index: number;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="mt-10 first:mt-0">
      <div className="font-ui text-[10px] font-bold uppercase tracking-[0.18em] text-claret">
        §{index}
      </div>
      <h2 className="mt-2 font-display text-[24px] font-bold leading-[1.25] text-ink">{title}</h2>
      <div className="mt-3 space-y-3 font-display text-[16px] leading-[1.7] text-ink">
        {children}
      </div>
    </section>
  );
}

export function DocumentCallout({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mt-5 rounded border border-rule border-l-[3px] border-l-claret bg-claret-soft px-5 py-4">
      <div className="font-ui text-[10px] font-bold uppercase tracking-[0.14em] text-claret">
        {label}
      </div>
      <div className="mt-2 font-display text-[15px] leading-[1.6] text-ink">{children}</div>
    </div>
  );
}

export function DocumentExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className="inline-flex rounded border border-claret bg-white px-4 py-2 font-ui text-[12.5px] font-bold text-claret hover:bg-claret-soft"
      rel="noreferrer"
      target="_blank"
    >
      {children}
    </a>
  );
}
