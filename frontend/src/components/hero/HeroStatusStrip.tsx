import type { CollectionListItem } from "@/lib/api/types";

export type HeroStatusStripProps = {
  activeCollection: CollectionListItem | null;
};

export function HeroStatusStrip({ activeCollection }: HeroStatusStripProps) {
  return (
    <p className="mt-3 text-center font-ui text-[12px] text-ink-muted">
      {activeCollection === null ? (
        <>
          Choose a collection below to enable search.{" "}
          <a href="#collections" className="text-claret underline-offset-4 hover:underline">
            View collections ↓
          </a>
        </>
      ) : (
        <>Currently searching in {activeCollection.display_name}.</>
      )}
    </p>
  );
}
