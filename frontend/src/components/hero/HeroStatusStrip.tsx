import { cn } from "@/lib/cn";
import type { CollectionListItem } from "@/lib/api/types";

export type HeroStatusStripProps = {
  activeCollection: CollectionListItem | null;
  chrome?: "default" | "landing-unified";
};

export function HeroStatusStrip({ activeCollection, chrome = "default" }: HeroStatusStripProps) {
  const showChoosePrompt = chrome === "landing-unified" || activeCollection === null;

  return (
    <p
      className={cn(
        "text-center font-ui text-[12px] text-ink-muted",
        chrome === "landing-unified" ? "border-t border-rule-soft bg-[#FBFAF7] px-6 py-3" : "mt-3",
      )}
    >
      {showChoosePrompt ? (
        <>
          {chrome === "landing-unified" ? (
            <span aria-hidden className="mr-1 opacity-70">
              ⓘ
            </span>
          ) : null}
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
