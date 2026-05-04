import { describe, expect, test } from "vitest";

import {
  buildDetailMetadataRows,
  buildLevelContext,
  buildQuestionCrumb,
  buildRowMetadataTags,
  getLevelPill,
} from "@/components/questions/questionDisplay";
import type { CollectionMetadataSchema } from "@/lib/api/types";

const schema: CollectionMetadataSchema = {
  version: 1,
  fields: [
    {
      key: "year",
      label: "Year",
      type: "integer",
      operators: ["eq"],
      exposed: true,
      source: null,
    },
    {
      key: "marks",
      label: "Marks",
      type: "integer",
      operators: ["eq"],
      exposed: true,
      source: null,
    },
    {
      key: "hidden",
      label: "Hidden",
      type: "string",
      operators: ["eq"],
      exposed: false,
      source: null,
    },
  ],
};

describe("questionDisplay", () => {
  test("derives truthful level pills", () => {
    expect(getLevelPill("question")).toEqual({ label: "Q", full: true });
    expect(getLevelPill("sub_question")).toEqual({ label: "Part", full: false });
  });

  test("builds crumbs from available metadata and sub-question label", () => {
    expect(buildQuestionCrumb({ paper_label: "Paper 1", question_label: "Q10" }, "(a)")).toBe(
      "Paper 1 · Q10 · (a)",
    );
  });

  test("omits absent crumb fields", () => {
    expect(buildQuestionCrumb({ year: 2024 }, null)).toBeNull();
  });

  test("limits row metadata tags to year and marks without schema labels", () => {
    expect(buildRowMetadataTags({ year: 2024, marks: 3, hidden: "x" }, schema)).toEqual([
      "2024",
      "3 marks",
    ]);
  });

  test("falls back to common row metadata without inventing labels", () => {
    expect(buildRowMetadataTags({ year: 2024, marks: 3, has_figure: true }, null)).toEqual([
      "2024",
      "3 marks",
    ]);
  });

  test("builds compact level context from question and sub-question metadata", () => {
    expect(buildLevelContext("question", { question_label: "Question 8" }, null)).toBe("8");
    expect(buildLevelContext("sub_question", { question_label: 8 }, "D")).toBe("D - Q 8");
    expect(buildLevelContext("sub_question", { question_label: "Q10" }, "(b)")).toBe("b - Q 10");
  });

  test("builds compact level context from deployed-style question metadata", () => {
    expect(buildLevelContext("question", { question: 2 }, null)).toBe("2");
    expect(buildLevelContext("sub_question", { question: 8 }, "D")).toBe("D - Q 8");
  });

  test("builds detail metadata rows from collection and available fields", () => {
    expect(
      buildDetailMetadataRows({
        collectionDisplay: "Cam Cs Tripos Fixture",
        metadata: { year: 2024, paper_label: "Paper 1", question_label: "Q10", marks: 3 },
        schema: null,
        subQuestionLabel: "(a)",
      }),
    ).toEqual([
      ["Collection", "Cam Cs Tripos Fixture"],
      ["Paper", "Paper 1"],
      ["Year", "2024"],
      ["Question", "Q10 (Part (a))"],
      ["Marks", "3"],
    ]);
  });

  test("uses source-backed schema fields for detail metadata rows", () => {
    expect(
      buildDetailMetadataRows({
        collectionDisplay: "Edinburgh",
        metadata: {
          course_code: "MECE10017",
          course_title: "Design of Surgical Tools",
          year: 2019,
        },
        schema: {
          version: 1,
          fields: [
            {
              key: "course",
              label: "Course",
              type: "string",
              operators: ["eq"],
              exposed: true,
              source: "course_code",
            },
            {
              key: "title",
              label: "Title",
              type: "string",
              operators: ["eq"],
              exposed: true,
              source: "course_title",
            },
          ],
        },
        subQuestionLabel: null,
      }),
    ).toEqual([
      ["Collection", "Edinburgh"],
      ["Course", "MECE10017"],
      ["Title", "Design of Surgical Tools"],
    ]);
  });
});
