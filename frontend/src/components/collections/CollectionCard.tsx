import type { CollectionListItem } from "@/lib/api/types";
import { cn } from "@/lib/cn";

export function CollectionCard({
  collection,
  isActive,
  isSignedIn,
  onPickAccessible,
  onPickLocked,
}: {
  collection: CollectionListItem;
  isActive: boolean;
  isSignedIn: boolean;
  onPickAccessible: (collection: CollectionListItem) => void;
  onPickLocked: (collection: CollectionListItem) => void;
}) {
  const locked =
    collection.access_state === "locked_requires_signin" ||
    collection.access_state === "locked_wrong_affiliation";

  const ariaLabel = [
    collection.display_name,
    isActive ? "Active scope" : "",
    locked ? "Locked" : "",
    collection.lock_reason ?? "",
  ]
    .filter(Boolean)
    .join(". ");

  return (
    <button
      type="button"
      onClick={() => (locked ? onPickLocked(collection) : onPickAccessible(collection))}
      aria-label={ariaLabel}
      aria-pressed={isActive}
      className={cn(
        "flex w-full flex-row items-center justify-between gap-4 rounded-sm border border-l-4 px-4 py-3 text-left transition-colors",
        "hover:bg-paper",
        isActive
          ? "selectable-selected"
          : cn(
              "border-l-transparent",
              locked ? "border-rule bg-paper-lock opacity-90" : "border-rule bg-paper-raised",
            ),
      )}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="font-display text-[15px] font-semibold text-ink">
            {collection.display_name}
          </h3>
          {isActive ? (
            <span className="font-ui text-[10px] uppercase tracking-widest text-claret">
              Active scope
            </span>
          ) : null}
        </div>
        <div
          className="mt-1 font-display text-xs uppercase tracking-wide text-ink-muted"
          style={{ fontVariant: "small-caps" }}
        >
          {buildAccessLine(collection, locked)}
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="font-display text-sm font-semibold text-ink">
          {collection.paper_count} papers
        </div>
        <div className="mt-1 font-display text-xs uppercase tracking-wide text-ink-muted">
          {buildYearRange(collection)}
        </div>
      </div>
      {/* isSignedIn is unused visually; kept in the API so parent logic can
          route locked_requires_signin for signed-in edge cases distinctly. */}
      {isSignedIn ? null : null}
    </button>
  );
}

function buildAccessLine(collection: CollectionListItem, locked: boolean): string {
  if (locked && collection.lock_reason) return collection.lock_reason;
  if (collection.community) return collection.community.display_name;
  return "Public";
}

function buildYearRange(collection: CollectionListItem): string {
  if (!collection.year_range) return "All years";
  return `${collection.year_range.start}–${String(collection.year_range.end).slice(-2)}`;
}
