import { Chip } from "@/components/shared/Chip";
import type { CollectionListItem } from "@/lib/api/types";

export function ScopeChip({
  collection,
  onOpen,
  open,
}: {
  collection: CollectionListItem | null;
  onOpen: () => void;
  open?: boolean;
}) {
  return (
    <Chip
      variant={collection ? "active" : "ghost"}
      onClick={onOpen}
      aria-haspopup
      {...(typeof open === "boolean" ? { "aria-expanded": open } : {})}
      title={collection ? collection.display_name : "Pick a collection"}
    >
      {collection ? collection.display_name : "Pick a collection"} ▾
    </Chip>
  );
}
