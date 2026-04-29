import type { CollectionListItem } from "@/lib/api/types";

export const publicCollection: CollectionListItem = {
  name: "public-demo",
  display_name: "MIT 6.006 (demo)",
  community: null,
  paper_count: 42,
  year_range: null,
  metadata_schema: {
    version: 1,
    fields: [
      {
        key: "year",
        label: "Year",
        type: "integer",
        operators: ["eq", "gte", "lte"],
        exposed: true,
        source: "chunk.year",
      },
    ],
  },
  access_state: "accessible",
  lock_reason: null,
};

export const cambridgeAccessible: CollectionListItem = {
  name: "cam-cs-tripos",
  display_name: "Cambridge CS Tripos",
  community: { id: "c-cam", display_name: "Cambridge" },
  paper_count: 744,
  year_range: { start: 2018, end: 2025 },
  metadata_schema: {
    version: 1,
    fields: [
      {
        key: "year",
        label: "Year",
        type: "integer",
        operators: ["eq", "gte", "lte"],
        exposed: true,
        source: "chunk.year",
      },
    ],
  },
  access_state: "accessible",
  lock_reason: null,
};

export const cambridgeLocked: CollectionListItem = {
  ...cambridgeAccessible,
  metadata_schema: null,
  access_state: "locked_requires_signin",
  lock_reason: "Sign in with Cambridge email to unlock",
};

export const edinburghAccessible: CollectionListItem = {
  name: "uoe-mece10017",
  display_name: "Uoe Mece10017",
  community: { id: "edinburgh", display_name: "Edinburgh" },
  paper_count: 1,
  year_range: { start: 2019, end: 2019 },
  metadata_schema: {
    version: 1,
    fields: [
      {
        key: "year",
        label: "Year",
        type: "integer",
        operators: ["eq", "gte", "lte"],
        exposed: true,
        source: "chunk.year",
      },
      {
        key: "course_code",
        label: "Course Code",
        type: "string",
        operators: ["eq"],
        exposed: true,
        source: "chunk.metadata.course_code",
      },
      {
        key: "course_title",
        label: "Course Title",
        type: "string",
        operators: ["eq"],
        exposed: true,
        source: "chunk.metadata.course_title",
      },
      {
        key: "document_id",
        label: "Document ID",
        type: "string",
        operators: ["eq"],
        exposed: false,
        source: "chunk.metadata.document_id",
      },
      {
        key: "question_number",
        label: "Question",
        type: "integer",
        operators: ["eq", "gte", "lte"],
        exposed: true,
        source: "chunk.question_number",
      },
      {
        key: "marks",
        label: "Marks",
        type: "integer",
        operators: ["eq", "gte", "lte"],
        exposed: true,
        source: "chunk.marks",
      },
      {
        key: "has_code",
        label: "Has Code",
        type: "boolean",
        operators: ["eq"],
        exposed: true,
        source: "chunk.has_code",
      },
      {
        key: "has_figure",
        label: "Has Figure",
        type: "boolean",
        operators: ["eq"],
        exposed: true,
        source: "chunk.has_figure",
      },
      {
        key: "has_table",
        label: "Has Table",
        type: "boolean",
        operators: ["eq"],
        exposed: true,
        source: "chunk.has_table",
      },
    ],
  },
  access_state: "accessible",
  lock_reason: null,
};

export const edinburghLocked: CollectionListItem = {
  ...edinburghAccessible,
  metadata_schema: null,
  access_state: "locked_requires_signin",
  lock_reason: "Sign in with Edinburgh email to unlock",
};

export const oxfordWrongAffiliation: CollectionListItem = {
  name: "ox-maths",
  display_name: "Oxford Mathematics",
  community: { id: "c-ox", display_name: "Oxford" },
  paper_count: 310,
  year_range: { start: 2019, end: 2025 },
  metadata_schema: null,
  access_state: "locked_wrong_affiliation",
  lock_reason: "Unavailable to your account",
};
