import type { FilterCondition, MetadataField } from "@/lib/api/types";

export function TextField({
  field,
  value,
  onChange,
}: {
  field: MetadataField;
  value: FilterCondition[];
  onChange: (next: FilterCondition[]) => void;
}) {
  const current = value.find((condition) => condition.field === field.key && condition.op === "eq");

  return (
    <label className="block">
      <span className="font-ui text-[10px] uppercase tracking-wider text-ink-muted">
        {field.label}
      </span>
      <input
        type={field.type === "integer" ? "number" : "text"}
        className="mt-1 w-full rounded-sm border border-rule bg-white px-2 py-1 text-sm"
        value={current?.value !== undefined ? String(current.value) : ""}
        onChange={(event) => {
          const raw = event.currentTarget.value;
          const others = value.filter(
            (condition) => !(condition.field === field.key && condition.op === "eq"),
          );
          const trimmed = raw.trim();

          if (trimmed === "") {
            onChange(others);
            return;
          }

          if (field.type === "integer") {
            const parsed = Number(trimmed);

            if (!Number.isInteger(parsed)) {
              onChange(others);
              return;
            }

            onChange([...others, { field: field.key, op: "eq", value: parsed }]);
            return;
          }

          onChange([...others, { field: field.key, op: "eq", value: raw }]);
        }}
      />
    </label>
  );
}
