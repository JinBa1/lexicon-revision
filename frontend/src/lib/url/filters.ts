import type {
  CollectionMetadataSchema,
  FilterCondition,
  MetadataFieldType,
  MetadataOperator,
} from "@/lib/api/types";

const ALLOWED_OPS: ReadonlySet<MetadataOperator> = new Set(["eq", "gte", "lte"]);

export type ParseResult =
  | { ok: true; conditions: FilterCondition[] }
  | {
      ok: false;
      reason:
        | "malformed"
        | "unknown_operator"
        | "unknown_field"
        | "empty_value"
        | "invalid_value_type";
      offending_field?: string;
      raw?: string;
    };

export function serializeFiltersToSearchParams(
  conditions: readonly FilterCondition[],
): URLSearchParams {
  const searchParams = new URLSearchParams();

  for (const condition of conditions) {
    const encodedValue = encodeURIComponent(stringifyValue(condition.value));
    searchParams.append("filter", `${condition.field}:${condition.op}:${encodedValue}`);
  }

  return searchParams;
}

export function parseFiltersFromSearchParams(
  params: URLSearchParams,
  schema: CollectionMetadataSchema | null,
): ParseResult {
  const conditions: FilterCondition[] = [];

  for (const raw of params.getAll("filter")) {
    const firstSeparator = raw.indexOf(":");
    if (firstSeparator <= 0) {
      return { ok: false, reason: "malformed", raw };
    }

    const secondSeparator = raw.indexOf(":", firstSeparator + 1);
    if (secondSeparator < 0) {
      return { ok: false, reason: "malformed", raw };
    }

    const field = raw.slice(0, firstSeparator);
    const op = raw.slice(firstSeparator + 1, secondSeparator);
    const encodedValue = raw.slice(secondSeparator + 1);

    if (op.length === 0) {
      return { ok: false, reason: "malformed", raw };
    }

    if (encodedValue.length === 0) {
      return { ok: false, reason: "empty_value", raw };
    }

    if (!ALLOWED_OPS.has(op as MetadataOperator)) {
      return { ok: false, reason: "unknown_operator", raw };
    }

    let decodedValue: string;
    try {
      decodedValue = decodeURIComponent(encodedValue);
    } catch {
      return { ok: false, reason: "malformed", raw };
    }

    if (decodedValue === "") {
      return { ok: false, reason: "empty_value", raw };
    }

    const fieldSchema = schema?.fields.find((candidate) => candidate.key === field);
    if (schema !== null && fieldSchema === undefined) {
      return {
        ok: false,
        reason: "unknown_field",
        offending_field: field,
        raw,
      };
    }

    const value = coerceValue(decodedValue, fieldSchema?.type ?? "string");
    if (value === undefined) {
      return {
        ok: false,
        reason: "invalid_value_type",
        offending_field: field,
        raw,
      };
    }

    conditions.push({
      field,
      op: op as MetadataOperator,
      value,
    });
  }

  return { ok: true, conditions };
}

function stringifyValue(value: FilterCondition["value"]): string {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }

  return String(value);
}

function coerceValue(raw: string, type: MetadataFieldType): FilterCondition["value"] | undefined {
  if (type === "integer") {
    if (!/^-?\d+$/.test(raw)) {
      return undefined;
    }

    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  if (type === "boolean") {
    if (raw === "true") {
      return true;
    }

    if (raw === "false") {
      return false;
    }

    return undefined;
  }

  return raw;
}
