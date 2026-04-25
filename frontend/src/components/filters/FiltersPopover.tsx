import { useEffect, useRef, type RefObject } from "react";

import { Button } from "@/components/shared/Button";
import type { CollectionMetadataSchema, FilterCondition } from "@/lib/api/types";

import { BooleanField } from "./fieldRenderers/BooleanField";
import { NumberRangeField } from "./fieldRenderers/NumberRangeField";
import { TextField } from "./fieldRenderers/TextField";

export function FiltersPopover({
  schema,
  value,
  onChange,
  onClose,
  closeBoundaryRef,
}: {
  schema: CollectionMetadataSchema | null;
  value: FilterCondition[];
  onChange: (next: FilterCondition[]) => void;
  onClose: () => void;
  closeBoundaryRef?: RefObject<HTMLElement | null>;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const exposedFields = schema?.fields.filter((field) => field.exposed) ?? [];

  useEffect(() => {
    function onDoc(event: MouseEvent) {
      const target = event.target as Node;
      if (closeBoundaryRef?.current?.contains(target)) {
        return;
      }

      if (ref.current && !ref.current.contains(target)) {
        onClose();
      }
    }

    document.addEventListener("click", onDoc);
    return () => document.removeEventListener("click", onDoc);
  }, [closeBoundaryRef, onClose]);

  if (exposedFields.length === 0) {
    return (
      <div
        ref={ref}
        className="absolute left-0 top-full z-10 mt-2 w-72 rounded-md border border-rule bg-paper-raised p-3 shadow-module"
      >
        <p className="font-body text-sm italic text-ink-muted">
          No filters available for this collection.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label="Filters"
      className="absolute left-0 top-full z-10 mt-2 w-80 space-y-4 rounded-md border border-rule bg-paper-raised p-4 shadow-module"
    >
      {exposedFields.map((field) => {
        if (
          field.type === "integer" &&
          field.operators.includes("gte") &&
          field.operators.includes("lte")
        ) {
          return (
            <NumberRangeField key={field.key} field={field} value={value} onChange={onChange} />
          );
        }

        if (field.type === "boolean" && field.operators.includes("eq")) {
          return <BooleanField key={field.key} field={field} value={value} onChange={onChange} />;
        }

        return <TextField key={field.key} field={field} value={value} onChange={onChange} />;
      })}
      <div className="flex items-center justify-between border-t border-rule pt-3">
        <Button variant="text" onClick={() => onChange([])}>
          Clear all
        </Button>
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      </div>
    </div>
  );
}
