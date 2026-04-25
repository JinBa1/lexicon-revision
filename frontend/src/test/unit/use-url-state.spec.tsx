import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test } from "vitest";

import type { CollectionMetadataSchema } from "@/lib/api/types";
import { useUrlState, type UrlState } from "@/lib/hooks/useUrlState";

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
  ],
};

function UrlStateProbe({ schema }: { schema: CollectionMetadataSchema | null }) {
  const state = useUrlState(schema);

  return <pre data-testid="url-state">{JSON.stringify(state)}</pre>;
}

function renderUrlState(initialEntry: string, schema: CollectionMetadataSchema | null): UrlState {
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <UrlStateProbe schema={schema} />
    </MemoryRouter>,
  );

  return JSON.parse(screen.getByTestId("url-state").textContent ?? "") as UrlState;
}

describe("useUrlState", () => {
  test("parses the query string from q", () => {
    const state = renderUrlState("/c/cam/questions?q=amortized+analysis", schema);

    expect(state.query).toBe("amortized analysis");
    expect(state.filterParse).toEqual({ ok: true, conditions: [] });
  });

  test("parses valid filters with schema coercion", () => {
    const state = renderUrlState(
      "/c/cam/questions?filter=year%3Agte%3A2020&filter=section%3Aeq%3Aalgorithms",
      schema,
    );

    expect(state.filterParse).toEqual({
      ok: true,
      conditions: [
        { field: "year", op: "gte", value: 2020 },
        { field: "section", op: "eq", value: "algorithms" },
      ],
    });
  });

  test("returns invalid filter parse results with schema", () => {
    const state = renderUrlState("/c/cam/questions?filter=author%3Aeq%3Asmith", schema);

    expect(state.filterParse).toEqual({
      ok: false,
      reason: "unknown_field",
      offending_field: "author",
      raw: "author:eq:smith",
    });
  });

  test("allows unknown fields when schema is null", () => {
    const state = renderUrlState("/c/cam/questions?filter=author%3Aeq%3Asmith", null);

    expect(state.filterParse).toEqual({
      ok: true,
      conditions: [{ field: "author", op: "eq", value: "smith" }],
    });
  });
});
