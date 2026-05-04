import type { CollectionMetadataSchema } from "@/lib/api/types";
import {
  formatMetadataValue,
  isRenderableValue,
  resolveMetadataFieldValue,
} from "@/lib/metadata/render";

export function getLevelPill(chunkLevel: "question" | "sub_question"): {
  label: string;
  full: boolean;
} {
  return chunkLevel === "question" ? { label: "Q", full: true } : { label: "Part", full: false };
}

export function buildQuestionCrumb(
  metadata: Record<string, unknown>,
  subQuestionLabel: string | null,
): string | null {
  const parts = [metadata.paper_label, metadata.question_label]
    .filter(isRenderableValue)
    .map(formatMetadataValue);
  if (subQuestionLabel) parts.push(subQuestionLabel);
  return parts.length > 0 ? parts.join(" · ") : null;
}

export function buildLevelContext(
  chunkLevel: "question" | "sub_question",
  metadata: Record<string, unknown>,
  subQuestionLabel: string | null,
): string | null {
  const questionNumber = formatQuestionNumber(getQuestionValue(metadata));
  const questionContext = questionNumber ? `Q ${questionNumber}` : null;
  if (chunkLevel === "question") return questionNumber;

  const part = formatPartContext(subQuestionLabel);
  return [part, questionContext].filter(isRenderableValue).join(" - ") || null;
}

export function buildRowMetadataTags(
  metadata: Record<string, unknown>,
  _schema: CollectionMetadataSchema | null | undefined,
): string[] {
  const tags: string[] = [];
  if (isRenderableValue(metadata.year)) tags.push(formatMetadataValue(metadata.year));
  if (isRenderableValue(metadata.marks)) tags.push(`${formatMetadataValue(metadata.marks)} marks`);
  return tags;
}

export function buildDetailMetadataRows({
  collectionDisplay,
  metadata,
  schema,
  subQuestionLabel,
}: {
  collectionDisplay: string;
  metadata: Record<string, unknown>;
  schema: CollectionMetadataSchema | null | undefined;
  subQuestionLabel: string | null;
}): [string, string][] {
  const rows: [string, string][] = [["Collection", collectionDisplay]];
  if (schema) {
    const schemaRows = schema.fields
      .filter((field) => field.exposed)
      .map((field): [string, string] | null => {
        const value = resolveMetadataFieldValue(metadata, field.key, field.source);
        return isRenderableValue(value) ? [field.label, formatMetadataValue(value)] : null;
      })
      .filter((value): value is [string, string] => value !== null);

    if (schemaRows.length > 0) {
      return [...rows, ...schemaRows];
    }
  }

  const paper = metadata.paper_label ?? metadata.paper;
  const year = metadata.year;
  const question = getQuestionValue(metadata);
  const marks = metadata.marks;

  if (isRenderableValue(paper)) rows.push(["Paper", formatMetadataValue(paper)]);
  if (isRenderableValue(year)) rows.push(["Year", formatMetadataValue(year)]);
  if (isRenderableValue(question)) {
    rows.push([
      "Question",
      `${formatMetadataValue(question)}${subQuestionLabel ? ` (Part ${subQuestionLabel})` : ""}`,
    ]);
  }
  if (isRenderableValue(marks)) rows.push(["Marks", formatMetadataValue(marks)]);
  return rows;
}

function getQuestionValue(metadata: Record<string, unknown>): unknown {
  return metadata.question_label ?? metadata.question ?? metadata.question_number ?? metadata.q;
}

function formatQuestionNumber(value: unknown): string | null {
  if (!isRenderableValue(value)) return null;

  const label = formatMetadataValue(value).trim();
  const expanded = label.match(/^question\s+(.+)$/i);
  if (expanded?.[1]) return expanded[1].trim();

  if (/^q\s*\S+/i.test(label)) {
    return label.replace(/^q\s*/i, "").trim();
  }

  return label;
}

function formatPartContext(value: string | null): string | null {
  if (!value) return null;

  const label = value
    .trim()
    .replace(/^\((.*)\)$/, "$1")
    .replace(/^part\s+/i, "")
    .trim();
  return label === "" ? null : label;
}
