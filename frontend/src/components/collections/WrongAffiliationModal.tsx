import { useEffect, useRef } from "react";

import type { CollectionListItem } from "@/lib/api/types";

export function WrongAffiliationModal({
  collection,
  onClose,
}: {
  collection: CollectionListItem | null;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    dialogRef.current?.focus();
  }, [collection]);

  if (!collection) {
    return null;
  }

  const title = `${collection.display_name} access mismatch`;
  const reason =
    collection.lock_reason ??
    "Your signed-in account is not currently affiliated with this collection.";

  return (
    <section
      ref={dialogRef}
      role="dialog"
      aria-modal="false"
      aria-labelledby="wrong-affiliation-title"
      tabIndex={-1}
      className="mb-6 rounded-sm border border-claret/30 bg-paper-raised p-5 shadow-sm"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="font-display text-[11px] font-semibold uppercase tracking-[0.18em] text-claret">
            Collection locked
          </p>
          <h2
            id="wrong-affiliation-title"
            className="mt-2 font-display text-lg font-semibold text-ink"
          >
            {title}
          </h2>
          <p className="mt-2 max-w-2xl font-display text-sm leading-6 text-ink-muted">
            Your signed-in account does not currently match the affiliation required for{" "}
            <span className="font-semibold text-ink">{collection.display_name}</span>.
          </p>
          <p className="mt-3 border-l-2 border-claret/50 pl-3 font-display text-sm text-claret">
            {reason}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="self-start rounded-sm border border-rule bg-paper px-3 py-1.5 font-display text-xs uppercase tracking-[0.12em] text-ink-muted transition-colors hover:border-claret hover:text-claret focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
          aria-label="Dismiss"
        >
          Dismiss
        </button>
      </div>
      <div className="mt-5 flex flex-col gap-3 border-t border-rule/70 pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="font-display text-xs text-ink-muted">
          Check the catalogue list if you need a different university scope.
        </p>
        <a
          href="#supported-universities"
          className="font-display text-sm font-semibold text-claret underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
        >
          Supported universities
        </a>
      </div>
    </section>
  );
}
