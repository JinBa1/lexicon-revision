import { useRef, useState } from "react";

import { FiltersPopover } from "@/components/filters/FiltersPopover";
import { Chip } from "@/components/shared/Chip";
import type { CollectionMetadataSchema, FilterCondition } from "@/lib/api/types";
import { cn } from "@/lib/cn";

export function FiltersChip({
  schema,
  value,
  onChange,
  chrome = "default",
}: {
  schema: CollectionMetadataSchema | null;
  value: FilterCondition[];
  onChange: (next: FilterCondition[]) => void;
  chrome?: "default" | "landing-unified" | "result-unified";
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const count = value.length;
  const isUnified = chrome === "landing-unified" || chrome === "result-unified";
  const label = isUnified
    ? count > 0
      ? `Filters (${count})`
      : "Filters"
    : count > 0
      ? `+ Filters (${count})`
      : "+ Filters";

  return (
    <div ref={rootRef} className={cn("relative", isUnified && "flex self-stretch")}>
      <Chip
        variant="ghost"
        className={
          isUnified
            ? "h-full min-h-14 rounded border-rule bg-white px-5 font-display text-base font-semibold text-ink"
            : undefined
        }
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup
        aria-expanded={open}
      >
        {isUnified ? <span aria-hidden>⚙</span> : null}
        {label}
      </Chip>
      {open ? (
        <FiltersPopover
          schema={schema}
          value={value}
          onChange={onChange}
          onClose={() => setOpen(false)}
          closeBoundaryRef={rootRef}
        />
      ) : null}
    </div>
  );
}
