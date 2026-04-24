import type { FilterCondition, MetadataField } from "@/lib/api/types";

export function NumberRangeField({
  field,
  value,
  onChange,
}: {
  field: MetadataField;
  value: FilterCondition[];
  onChange: (next: FilterCondition[]) => void;
}) {
  const gte = value.find((condition) => condition.field === field.key && condition.op === "gte");
  const lte = value.find((condition) => condition.field === field.key && condition.op === "lte");

  function update(op: "gte" | "lte", raw: string) {
    const others = value.filter(
      (condition) => !(condition.field === field.key && condition.op === op),
    );
    const trimmed = raw.trim();

    if (trimmed === "") {
      onChange(others);
      return;
    }

    const parsed = Number(trimmed);

    if (!Number.isInteger(parsed)) {
      onChange(others);
      return;
    }

    const ordered: FilterCondition[] = [];
    for (const condition of value) {
      if (condition.field === field.key && condition.op === op) {
        continue;
      }

      ordered.push(condition);
    }

    ordered.push({ field: field.key, op, value: parsed });
    onChange(ordered);
  }

  return (
    <div>
      <span className="font-ui text-[10px] uppercase tracking-wider text-ink-muted">
        {field.label}
      </span>
      <div className="mt-1 flex gap-2">
        <input
          type="number"
          aria-label={`${field.label} from`}
          placeholder="From"
          className="w-full rounded-sm border border-rule bg-white px-2 py-1 text-sm"
          value={gte ? String(gte.value) : ""}
          onChange={(event) => update("gte", event.currentTarget.value)}
        />
        <input
          type="number"
          aria-label={`${field.label} to`}
          placeholder="To"
          className="w-full rounded-sm border border-rule bg-white px-2 py-1 text-sm"
          value={lte ? String(lte.value) : ""}
          onChange={(event) => update("lte", event.currentTarget.value)}
        />
      </div>
    </div>
  );
}
