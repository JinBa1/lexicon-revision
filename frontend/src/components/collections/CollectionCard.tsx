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
        "flex w-full flex-row items-center gap-5 rounded border border-l-4 px-4 py-4 text-left transition-colors sm:px-6",
        "hover:border-claret hover:bg-paper-raised",
        isActive
          ? "selectable-selected"
          : cn(
              "border-rule border-l-transparent",
              locked ? "border-rule bg-paper-lock opacity-90" : "border-rule bg-paper-raised",
            ),
      )}
    >
      <span
        aria-hidden
        className={cn(
          "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-rule",
          isActive && "border-claret",
        )}
      >
        <span className={cn("h-2.5 w-2.5 rounded-full bg-claret", isActive ? "block" : "hidden")} />
      </span>
      <div className="min-w-0 flex-1">
        <div
          className={cn(
            "font-ui text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-muted",
            locked && !isActive && "text-claret",
          )}
        >
          {buildMetaLine(collection, locked)}
        </div>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="font-display text-xl font-semibold leading-tight text-ink">
            {collection.display_name}
          </h3>
          {isActive ? (
            <span className="font-ui text-[10px] uppercase tracking-widest text-claret">
              Active scope
            </span>
          ) : null}
        </div>
      </div>
      <span aria-hidden className="shrink-0 pl-1 font-display text-2xl font-light text-rule">
        ›
      </span>
      {/* isSignedIn is unused visually; kept in the API so parent logic can
          route locked_requires_signin for signed-in edge cases distinctly. */}
      {isSignedIn ? null : null}
    </button>
  );
}

function buildMetaLine(collection: CollectionListItem, locked: boolean): string {
  if (locked) return buildAccessLine(collection, locked);
  return `${buildAccessLine(collection, locked)} · ${collection.paper_count} papers · ${buildYearRange(
    collection,
  )}`;
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
