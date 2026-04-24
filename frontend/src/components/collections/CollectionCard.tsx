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
        "flex w-full flex-col rounded-sm border p-4 text-left",
        "hover:border-claret",
        locked ? "border-rule bg-paper-lock opacity-90" : "border-rule bg-paper-raised",
        isActive && "border-2 border-claret bg-claret-soft",
      )}
    >
      <h3 className="font-display text-[15px] font-semibold text-ink">{collection.display_name}</h3>
      <div
        className="mt-1 font-display text-xs uppercase tracking-wide text-ink-muted"
        style={{ fontVariant: "small-caps" }}
      >
        {buildMetaLine(collection)}
      </div>
      {locked && collection.lock_reason ? (
        <div className="mt-2 border-t border-dashed border-rule-soft pt-2 font-display text-[11px] text-claret">
          {collection.lock_reason}
        </div>
      ) : null}
      {isActive ? (
        <div className="mt-2 font-ui text-[10px] uppercase tracking-widest text-claret">
          ● Active scope
        </div>
      ) : null}
      {/* isSignedIn is unused visually; kept in the API so parent logic can
          route locked_requires_signin for signed-in edge cases distinctly. */}
      {isSignedIn ? null : null}
    </button>
  );
}

function buildMetaLine(collection: CollectionListItem): string {
  const parts: string[] = [];
  if (collection.community) parts.push(collection.community.display_name);
  else parts.push("Public");
  parts.push(`${collection.paper_count} papers`);
  if (collection.year_range) {
    parts.push(`${collection.year_range.start}–${String(collection.year_range.end).slice(-2)}`);
  }
  return parts.join(" · ");
}
