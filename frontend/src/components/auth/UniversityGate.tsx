import { useState } from "react";

import { Link } from "react-router-dom";

import { Button } from "@/components/shared/Button";
import type { SupportedUniversity } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { PROJECT_DISCUSSIONS_URL } from "@/lib/publicCopy";

export function UniversityGate({
  universities,
  initialSelected,
  onContinue,
}: {
  universities: SupportedUniversity[];
  initialSelected: string | null;
  onContinue: (universityId: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(initialSelected);
  const selectedUniversity = universities.find((university) => university.id === selected) ?? null;
  const selectedDomains = selectedUniversity?.email_domains ?? [];
  const selectedDomainText = formatEmailDomains(selectedDomains);

  return (
    <main className="mx-auto max-w-[880px] px-6 py-12 pb-20 sm:px-8">
      <div className="flex flex-col items-start gap-2">
        <Link to="/" className="font-ui text-[12.5px] font-semibold text-claret hover:underline">
          ← Back to home
        </Link>
        <div className="font-ui text-[11px] font-bold uppercase tracking-[0.22em] text-claret">
          Sign-up · Step 1 of 2
        </div>
      </div>
      <h1 className="mt-3 font-display text-[38px] font-bold leading-[1.2] text-ink">
        Join your student community
      </h1>
      <p className="mt-4 max-w-[60ch] font-display text-[17px] leading-[1.6] text-ink-muted">
        Communities are scoped to universities we currently support. Pick yours to continue with
        your university email domain.
      </p>

      <SectionHeader label="Supported communities" className="mt-10" />

      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {universities.map((university) => {
          const isSelected = selected === university.id;

          return (
            <li key={university.id}>
              <button
                type="button"
                aria-pressed={isSelected}
                onClick={() => setSelected(university.id)}
                className={cn(
                  "relative flex min-h-36 w-full flex-col gap-2 rounded-md border bg-paper-raised p-6 text-left transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 focus-visible:ring-offset-paper",
                  isSelected
                    ? "border-claret border-l-4 bg-claret-active pl-5"
                    : "border-rule hover:border-claret",
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    "absolute right-4 top-4 hidden h-6 w-6 items-center justify-center rounded-full bg-claret font-ui text-xs font-bold text-white",
                    isSelected && "flex",
                  )}
                >
                  ✓
                </span>
                <span className="block pr-8 font-display text-[19px] font-bold leading-tight text-ink">
                  {university.display_name}
                </span>
                <span className="block font-mono text-[12px] uppercase tracking-[0.08em] text-ink-muted">
                  {university.email_domains.join(" / ")}
                </span>
                <span className="mt-1 flex flex-wrap gap-1.5">
                  <span className="rounded-[3px] border border-rule-soft bg-white px-2 py-0.5 font-ui text-[10.5px] tracking-[0.04em] text-ink-muted">
                    University email required
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <div className="mt-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-end">
        <span className="font-ui text-xs text-ink-muted">
          {selectedDomainText ? (
            <>
              You'll verify with {selectedDomains.length > 1 ? "one of " : "a "}
              <strong className="font-semibold text-ink">{selectedDomainText}</strong>{" "}
              {selectedDomains.length > 1 ? "email domains" : "email"} next.
            </>
          ) : (
            <>
              {/* This phrase is completed by the adjacent "Continue" button. */}
              Choose a university to
            </>
          )}
        </span>
        <Button
          variant="primary"
          className="rounded bg-claret px-6 py-3 font-ui text-[13.5px] font-bold text-white shadow-[0_2px_8px_rgba(126,46,46,0.18)]"
          disabled={!selected}
          onClick={() => {
            if (selected) {
              onContinue(selected);
            }
          }}
        >
          Continue →
        </Button>
      </div>

      <SectionHeader label="Don't see your university?" className="mt-14" />
      <div className="rounded-md border border-dashed border-rule bg-paper-raised px-6 py-6">
        <div className="font-ui text-[10px] font-bold uppercase tracking-[0.18em] text-claret">
          Coming soon
        </div>
        <h2 className="mt-2 font-display text-[20px] font-bold text-ink">
          Start a community for your university
        </h2>
        <p className="mt-3 max-w-[55ch] font-display text-[15px] leading-[1.55] text-ink-muted">
          Self-serve community creation isn't open yet. While the portal is being built, we onboard
          new universities by hand. Reach out and we'll set up a community for your school.
        </p>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled
            className="inline-flex cursor-not-allowed items-center gap-2 rounded border border-rule bg-white px-4 py-2 font-ui text-[12.5px] font-semibold text-ink-muted opacity-85"
          >
            <span aria-hidden>➕</span>
            <span>Create a community</span>
            <span className="rounded-[3px] bg-paper-sunken px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em]">
              Soon
            </span>
          </button>
          <a
            href={PROJECT_DISCUSSIONS_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded border border-claret bg-white px-4 py-2 font-ui text-[12.5px] font-bold text-claret hover:bg-claret-soft"
          >
            ✉ Contact support
          </a>
        </div>
      </div>
    </main>
  );
}

function SectionHeader({ label, className }: { label: string; className?: string }) {
  return (
    <div className={cn("mb-4 flex items-center gap-4", className)}>
      <span className="whitespace-nowrap font-ui text-[11.5px] font-bold uppercase tracking-[0.18em] text-ink">
        {label}
      </span>
      <span className="h-px flex-1 bg-rule-soft" />
    </div>
  );
}

function formatEmailDomains(domains: string[]): string | null {
  if (domains.length === 0) {
    return null;
  }

  if (domains.length === 1) {
    return domains[0] ?? null;
  }

  if (domains.length === 2) {
    return domains.join(" or ");
  }

  const lastDomain = domains[domains.length - 1];
  if (!lastDomain) {
    return domains.join(", ");
  }

  return `${domains.slice(0, -1).join(", ")}, or ${lastDomain}`;
}
