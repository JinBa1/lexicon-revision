import type { CollectionMetadataSchema } from "@/lib/api/types";

export type MetadataSummaryOptions = {
  schema?: CollectionMetadataSchema | null;
  subLabel?: string | null;
};

export function renderMetadataSummary(
  metadata: Record<string, unknown>,
  options: MetadataSummaryOptions = {},
): string {
  const values = renderMetadataValues(metadata, options.schema);

  if (options.subLabel) {
    values.push(options.subLabel);
  }

  return values.join(" / ");
}

function renderMetadataValues(
  metadata: Record<string, unknown>,
  schema?: CollectionMetadataSchema | null,
): string[] {
  if (!schema) {
    return renderGenericValues(metadata);
  }

  const schemaValues = renderSchemaValues(metadata, schema);
  return schemaValues.length > 0 ? schemaValues : renderGenericValues(metadata);
}

function renderSchemaValues(
  metadata: Record<string, unknown>,
  schema: CollectionMetadataSchema,
): string[] {
  return schema.fields
    .filter((field) => field.exposed)
    .map((field) => {
      return resolveMetadataFieldValue(metadata, field.key, field.source);
    })
    .filter(isRenderableValue)
    .map(formatMetadataValue);
}

function renderGenericValues(metadata: Record<string, unknown>): string[] {
  return Object.keys(metadata)
    .sort((a, b) => a.localeCompare(b))
    .map((key) => {
      const value = metadata[key];
      if (!isRenderableValue(value)) {
        return null;
      }
      return `${humanizeKey(key)}: ${formatMetadataValue(value)}`;
    })
    .filter((value): value is string => value !== null);
}

export function resolveMetadataFieldValue(
  metadata: Record<string, unknown>,
  key: string,
  source: string | null,
): unknown {
  const directValue = metadata[key];
  if (isRenderableValue(directValue) || source === null) {
    return directValue;
  }

  const sourceValue = metadata[source];
  if (isRenderableValue(sourceValue)) {
    return sourceValue;
  }

  return metadata[source.replace(/^chunk\./, "")];
}

export function isRenderableValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== "";
}

export function formatMetadataValue(value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }

  return JSON.stringify(value);
}

function humanizeKey(key: string): string {
  return key.replaceAll("_", " ");
}
