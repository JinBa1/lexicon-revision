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
    <section className="mt-14">
      <div className="mb-7 flex items-center gap-5">
        <h2 className="font-ui text-xs font-bold uppercase tracking-[0.2em] text-ink">
          Collections
        </h2>
        <div data-testid="collections-header-rule" className="h-px flex-1 bg-rule-soft" />
      </div>
      <div data-collection-rows className="flex flex-col gap-3.5">
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
