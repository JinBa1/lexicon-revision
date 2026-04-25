import { describe, expect, test } from "vitest";

import { parseFiltersFromSearchParams, serializeFiltersToSearchParams } from "@/lib/url/filters";
import type { CollectionMetadataSchema, FilterCondition } from "@/lib/api/types";

const schema: CollectionMetadataSchema = {
  version: 1,
  fields: [
    {
      key: "year",
      label: "Year",
      type: "integer",
      operators: ["eq", "gte", "lte"],
      exposed: true,
      source: null,
    },
    {
      key: "section",
      label: "Section",
      type: "string",
      operators: ["eq"],
      exposed: true,
      source: null,
    },
    {
      key: "has_figure",
      label: "Has figure",
      type: "boolean",
      operators: ["eq"],
      exposed: true,
      source: null,
    },
  ],
};

describe("filter URL serialization", () => {
  test("round-trips simple conditions", () => {
    const conditions: FilterCondition[] = [
      { field: "year", op: "eq", value: 2022 },
      { field: "section", op: "eq", value: "data-structures" },
    ];

    const sp = serializeFiltersToSearchParams(conditions);

    expect(sp.getAll("filter")).toEqual(["year:eq:2022", "section:eq:data-structures"]);

    const parsed = parseFiltersFromSearchParams(sp, schema);

    expect(parsed.ok).toBe(true);
    expect(parsed.ok && parsed.conditions).toEqual(conditions);
  });

  test("preserves order with range pairs on the same field", () => {
    const conditions: FilterCondition[] = [
      { field: "year", op: "gte", value: 2018 },
      { field: "year", op: "lte", value: 2025 },
    ];

    const sp = serializeFiltersToSearchParams(conditions);

    expect(sp.getAll("filter")).toEqual(["year:gte:2018", "year:lte:2025"]);

    const parsed = parseFiltersFromSearchParams(sp, schema);

    expect(parsed.ok && parsed.conditions).toEqual(conditions);
  });

  test("encodes reserved characters in values", () => {
    const conditions: FilterCondition[] = [{ field: "section", op: "eq", value: "a:b;c,d&e=f" }];

    const sp = serializeFiltersToSearchParams(conditions);
    const raw = sp.getAll("filter")[0];

    expect(raw).toBe(`section:eq:${encodeURIComponent("a:b;c,d&e=f")}`);

    const parsed = parseFiltersFromSearchParams(sp, schema);

    expect(parsed.ok && parsed.conditions[0]?.value).toBe("a:b;c,d&e=f");
  });

  test("round-trips after page-level URLSearchParams encoding", () => {
    const conditions: FilterCondition[] = [
      { field: "section", op: "eq", value: "a:b;c,d&e=f?x#y%z" },
    ];
    const filterParams = serializeFiltersToSearchParams(conditions);
    const pageParams = new URLSearchParams();

    for (const filter of filterParams.getAll("filter")) {
      pageParams.append("filter", filter);
    }

    expect(pageParams.toString()).toContain("a%253Ab");
    expect(pageParams.toString()).toContain("%2525z");

    const parsed = parseFiltersFromSearchParams(new URLSearchParams(pageParams.toString()), schema);

    expect(parsed.ok && parsed.conditions).toEqual(conditions);
  });

  test("encodes unicode values", () => {
    const conditions: FilterCondition[] = [{ field: "section", op: "eq", value: "概率论" }];

    const sp = serializeFiltersToSearchParams(conditions);
    const parsed = parseFiltersFromSearchParams(sp, schema);

    expect(parsed.ok && parsed.conditions[0]?.value).toBe("概率论");
  });

  test("boolean values round-trip as 'true'/'false'", () => {
    const conditions: FilterCondition[] = [
      { field: "has_figure", op: "eq", value: true },
      { field: "has_figure", op: "eq", value: false },
    ];

    const sp = serializeFiltersToSearchParams(conditions);

    expect(sp.getAll("filter")).toEqual(["has_figure:eq:true", "has_figure:eq:false"]);

    const parsed = parseFiltersFromSearchParams(sp, schema);

    expect(parsed.ok).toBe(true);
    expect(parsed.ok && parsed.conditions).toEqual(conditions);
  });

  test("invalid format returns parse error", () => {
    const sp = new URLSearchParams();
    sp.append("filter", "year:eq");

    const parsed = parseFiltersFromSearchParams(sp, schema);

    expect(parsed.ok).toBe(false);
    expect(!parsed.ok && parsed.reason).toBe("malformed");
  });

  test("empty operator segment returns malformed", () => {
    const sp = new URLSearchParams();
    sp.append("filter", "year::2022");

    const parsed = parseFiltersFromSearchParams(sp, schema);

    expect(parsed.ok).toBe(false);
    expect(!parsed.ok && parsed.reason).toBe("malformed");
  });

  test("unknown operator returns parse error", () => {
    const sp = new URLSearchParams();
    sp.append("filter", "year:in:2022");

    const parsed = parseFiltersFromSearchParams(sp, schema);

    expect(parsed.ok).toBe(false);
    expect(!parsed.ok && parsed.reason).toBe("unknown_operator");
  });

  test("unknown field returns parse error with offending field", () => {
    const sp = new URLSearchParams();
    sp.append("filter", "author:eq:smith");

    const parsed = parseFiltersFromSearchParams(sp, schema);

    expect(parsed.ok).toBe(false);

    if (!parsed.ok) {
      expect(parsed.reason).toBe("unknown_field");
      expect(parsed.offending_field).toBe("author");
    }
  });

  test("empty value is rejected", () => {
    const sp = new URLSearchParams();
    sp.append("filter", "section:eq:");

    const parsed = parseFiltersFromSearchParams(sp, schema);

    expect(parsed.ok).toBe(false);
    expect(!parsed.ok && parsed.reason).toBe("empty_value");
  });

  test("integer field with non-numeric value is rejected", () => {
    const sp = new URLSearchParams();
    sp.append("filter", "year:eq:notanumber");

    const parsed = parseFiltersFromSearchParams(sp, schema);

    expect(parsed.ok).toBe(false);
    expect(!parsed.ok && parsed.reason).toBe("invalid_value_type");
  });
});
