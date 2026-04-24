import type { FilterCondition, MetadataField } from "@/lib/api/types";

export function BooleanField({
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
      <select
        className="mt-1 w-full rounded-sm border border-rule bg-white px-2 py-1 text-sm"
        value={typeof current?.value === "boolean" ? String(current.value) : ""}
        onChange={(event) => {
          const raw = event.currentTarget.value;
          const others = value.filter(
            (condition) => !(condition.field === field.key && condition.op === "eq"),
          );

          if (raw.trim() === "") {
            onChange(others);
            return;
          }

          onChange([...others, { field: field.key, op: "eq", value: raw === "true" }]);
        }}
      >
        <option value="">Any</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    </label>
  );
}
