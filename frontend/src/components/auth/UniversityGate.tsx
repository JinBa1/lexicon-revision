import { useState } from "react";

import { Button } from "@/components/shared/Button";
import type { SupportedUniversity } from "@/lib/api/types";
import { cn } from "@/lib/cn";

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

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-display text-3xl font-semibold text-ink">Pick your university</h1>
      <p className="mt-2 font-body text-ink-muted">
        Sign-up is open to maintainer-supported universities. Pick yours to continue.
      </p>
      <ul className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {universities.map((university) => (
          <li key={university.id}>
            <button
              type="button"
              aria-pressed={selected === university.id}
              onClick={() => setSelected(university.id)}
              className={cn(
                "min-h-28 w-full rounded-sm border bg-paper-raised p-4 text-left transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 focus-visible:ring-offset-paper",
                selected === university.id
                  ? "border-2 border-claret bg-claret-soft"
                  : "border-rule hover:border-claret/60",
              )}
            >
              <span className="block font-display text-[15px] font-semibold text-ink">
                {university.display_name}
              </span>
              <span
                className="mt-1 block font-ui text-xs uppercase tracking-[0.16em] text-ink-muted"
                style={{ fontVariant: "small-caps" }}
              >
                {university.email_domains.join(" / ")}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-6 flex justify-end">
        <Button
          variant="primary"
          disabled={!selected}
          onClick={() => {
            if (selected) {
              onContinue(selected);
            }
          }}
        >
          Continue
        </Button>
      </div>
    </main>
  );
}
