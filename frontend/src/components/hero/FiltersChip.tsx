import { useState } from "react";

import { FiltersPopover } from "@/components/filters/FiltersPopover";
import { Chip } from "@/components/shared/Chip";
import type { CollectionMetadataSchema, FilterCondition } from "@/lib/api/types";

export function FiltersChip({
  schema,
  value,
  onChange,
}: {
  schema: CollectionMetadataSchema | null;
  value: FilterCondition[];
  onChange: (next: FilterCondition[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const count = value.length;

  return (
    <div className="relative">
      <Chip
        variant="ghost"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup
        aria-expanded={open}
      >
        {count > 0 ? `+ Filters (${count})` : "+ Filters"}
      </Chip>
      {open ? (
        <FiltersPopover
          schema={schema}
          value={value}
          onChange={onChange}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </div>
  );
}
