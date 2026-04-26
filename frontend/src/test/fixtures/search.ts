import type { ChunkDetail, SearchResult, StudySource } from "@/lib/api/types";

export const questionResult: SearchResult = {
  chunk_id: "cam-2022-p5-q3",
  chunk_level: "question",
  parent_chunk_id: null,
  sub_question_label: null,
  text: "Give an amortized analysis of successive insertions into a dynamic array that doubles on overflow.",
  score: 0.88,
  metadata: { year: 2022, paper_label: "Paper 5", question_label: "Question 3", has_figure: true },
  media: [],
  render_blocks: null,
};

export const subQuestionResult: SearchResult = {
  chunk_id: "cam-2022-p5-q3-b",
  chunk_level: "sub_question",
  parent_chunk_id: "cam-2022-p5-q3",
  sub_question_label: "(b)",
  text: "Extend your analysis to the case where the array halves on underflow.",
  score: 0.84,
  metadata: { year: 2022, paper_label: "Paper 5", question_label: "Question 3", has_figure: true },
  media: [],
  render_blocks: null,
};

export const chunkDetailFixture: ChunkDetail = {
  chunk_id: "cam-2022-p5-q3-b",
  chunk_level: "sub_question",
  parent_chunk_id: "cam-2022-p5-q3",
  sub_question_label: "(b)",
  text: "Extend your analysis to the case where the array halves on underflow.",
  metadata: { year: 2022, paper_label: "Paper 5", question_label: "Question 3", has_figure: true },
  media: [],
  collection: "cam-cs-tripos",
  parent: {
    text: "Give an amortized analysis of successive insertions into a dynamic array that doubles on overflow.",
    metadata: {
      year: 2022,
      paper_label: "Paper 5",
      question_label: "Question 3",
      has_figure: true,
    },
    render_blocks: null,
  },
  render_blocks: null,
};

export const studySource: StudySource = {
  chunk_id: "cam-2022-p5-q3",
  chunk_level: "question",
  parent_chunk_id: null,
  sub_question_label: null,
  score: 0.88,
  excerpt: "Give an amortized analysis of successive insertions…",
  metadata: { year: 2022, paper_label: "Paper 5", question_label: "Question 3", has_figure: true },
  why_cited: "Canonical accounting-method setup on dynamic arrays.",
  excerpt_blocks: null,
};
