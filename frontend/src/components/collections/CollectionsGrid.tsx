import type { CollectionListItem } from "@/lib/api/types";
import { CollectionCard } from "./CollectionCard";

export function CollectionsGrid({
  collections,
  activeName,
  isSignedIn,
  onPickAccessible,
  onPickLocked,
}: {
  collections: CollectionListItem[];
  activeName: string | null;
  isSignedIn: boolean;
  onPickAccessible: (collection: CollectionListItem) => void;
  onPickLocked: (collection: CollectionListItem) => void;
}) {
  return (
    <section className="mt-10 border-t border-rule/50 pt-8">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="font-display text-sm font-semibold uppercase tracking-[0.18em] text-ink">
          Collections
        </h2>
        <span className="font-display text-[11px] uppercase tracking-[0.1em] text-ink-muted">
          Click to change scope
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {collections.map((collection) => (
          <CollectionCard
            key={collection.name}
            collection={collection}
            isActive={activeName === collection.name}
            isSignedIn={isSignedIn}
            onPickAccessible={onPickAccessible}
            onPickLocked={onPickLocked}
          />
        ))}
      </div>
    </section>
  );
}
