import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import type {
  ChunkDetail,
  CollectionListItem,
  SearchRequest,
  SearchResponse,
  StudyRequest,
  StudyResponse,
  SupportedUniversity,
} from "@/lib/api/types";

const publicCollection: CollectionListItem = {
  name: "public-demo",
  display_name: "Public Graphs Demo",
  community: null,
  paper_count: 8,
  year_range: { start: 2020, end: 2025 },
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

const privateCollection: CollectionListItem = {
  name: "private-demo",
  display_name: "Private Demo Papers",
  community: { id: "demo-university", display_name: "Demo University" },
  paper_count: 16,
  year_range: { start: 2018, end: 2025 },
  metadata_schema: null,
  access_state: "locked_requires_signin",
  lock_reason: "Sign in with Demo University email to unlock",
};

const supportedUniversities: SupportedUniversity[] = [
  {
    id: "demo-university",
    display_name: "Demo University",
    email_domains: ["demo.edu"],
  },
];

const searchResponse: SearchResponse = {
  query: "graphs",
  collection: "public-demo",
  total: 2,
  results: [
    {
      chunk_id: "chunk-1",
      chunk_level: "question",
      parent_chunk_id: null,
      sub_question_label: null,
      text: "Compare breadth-first search and depth-first search on a directed graph.",
      score: 0.94,
      metadata: {
        year: 2025,
        paper_label: "Algorithms",
        question_label: "Question 1",
      },
      media: [],
      render_blocks: null,
    },
    {
      chunk_id: "chunk-2",
      chunk_level: "sub_question",
      parent_chunk_id: "chunk-1",
      sub_question_label: "(b)",
      text: "Explain how predecessor links recover a shortest path tree.",
      score: 0.87,
      metadata: {
        year: 2024,
        paper_label: "Algorithms",
        question_label: "Question 2",
      },
      media: [],
      render_blocks: null,
    },
  ],
};

const focusedChunk: ChunkDetail = {
  chunk_id: "chunk-1",
  chunk_level: "question",
  parent_chunk_id: null,
  sub_question_label: null,
  text: "Full source text for a graph traversal question comparing breadth-first search, depth-first search, and when each traversal discovers vertices.",
  metadata: {
    year: 2025,
    paper_label: "Algorithms",
    question_label: "Question 1",
  },
  media: [],
  collection: "public-demo",
  parent: null,
  render_blocks: null,
};

const chunkDetails: Record<string, ChunkDetail> = {
  "chunk-1": focusedChunk,
  "chunk-2": {
    chunk_id: "chunk-2",
    chunk_level: "sub_question",
    parent_chunk_id: "chunk-1",
    sub_question_label: "(b)",
    text: "Explain how predecessor links recover a shortest path tree after running breadth-first search.",
    metadata: {
      year: 2024,
      paper_label: "Algorithms",
      question_label: "Question 2",
    },
    media: [],
    collection: "public-demo",
    parent: {
      text: "Compare breadth-first search and depth-first search on a directed graph.",
      metadata: {
        year: 2025,
        paper_label: "Algorithms",
        question_label: "Question 1",
      },
      render_blocks: null,
    },
    render_blocks: null,
  },
};

const studyResponse: StudyResponse = {
  schema_version: "study_answer_v2",
  request_id: "study-graphs-1",
  query: "graphs",
  scope: { collection: "public-demo" },
  answer_status: "ok",
  answer: {
    overview:
      "Graph traversal questions usually ask you to connect the data structure choice to the order in which vertices are discovered.",
    patterns: [
      {
        label: "Traversal invariant",
        summary:
          "State what the queue or stack contains, then use that invariant to prove the discovery order.",
        supporting_chunk_ids: ["chunk-1"],
      },
    ],
    limitations: ["This answer is based on the public demo graph questions only."],
  },
  sources: [
    {
      chunk_id: "chunk-1",
      chunk_level: "question",
      parent_chunk_id: null,
      sub_question_label: null,
      score: 0.94,
      excerpt: "Compare breadth-first search and depth-first search on a directed graph.",
      metadata: {
        year: 2025,
        paper_label: "Algorithms",
        question_label: "Question 1",
      },
      why_cited: "It directly asks for the graph traversal comparison.",
      excerpt_blocks: null,
    },
  ],
  retrieval: {
    status: "ok",
    top_k: 15,
    returned_result_count: 1,
    context_budget_tokens: 4000,
    context_chunk_ids: ["chunk-1"],
    omitted_chunk_ids: [],
    truncated_chunk_ids: [],
    filters_applied: [],
    rerank: true,
  },
  planning: {
    status: "ok",
    planner_version: "planner-v1",
    original_query: "graphs",
    semantic_queries: ["graph traversal exam questions"],
    intent: "content_retrieval",
    error_category: null,
    latency_ms: 11,
  },
  generation: {
    provider: "mock",
    model: "mock-study-model",
    prompt_version: "study-v2",
    temperature: 0,
    attempt_count: 1,
    citation_drops: 0,
    error_category: null,
    latency_ms: 24,
  },
};

async function stubFrontendContract(page: Page) {
  await page.route("**/collections", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([publicCollection, privateCollection]),
    });
  });

  await page.route("**/supported-universities", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(supportedUniversities),
    });
  });

  await page.route("**/search", async (route) => {
    const request = route.request().postDataJSON() as SearchRequest;

    expect(request).toMatchObject({
      query: "graphs",
      collection: "public-demo",
      filters: [],
      limit: 15,
      rerank: true,
    });

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(searchResponse),
    });
  });

  await page.route("**/study", async (route) => {
    const request = route.request().postDataJSON() as StudyRequest;

    expect(request).toMatchObject({
      query: "graphs",
      scope: { collection: "public-demo" },
      filters: [],
      top_k: 15,
    });

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(studyResponse),
    });
  });

  await page.route("**/collections/public-demo/chunks/*", async (route) => {
    const chunkId = route.request().url().split("/").pop() ?? "";
    const detail = chunkDetails[chunkId];

    await route.fulfill({
      status: detail ? 200 : 404,
      contentType: "application/json",
      body: JSON.stringify(detail ?? { detail: "Not found" }),
    });
  });
}

async function assertNoCriticalAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const criticalViolations = results.violations.filter(
    (violation) => violation.impact === "critical",
  );

  expect(criticalViolations).toEqual([]);
}

test.beforeEach(async ({ page }) => {
  await stubFrontendContract(page);
});

test.describe("critical axe accessibility", () => {
  test("has no critical axe violations on /", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Public Graphs Demo")).toBeVisible();

    await assertNoCriticalAxeViolations(page);
  });

  test("has no critical axe violations on /sign-up", async ({ page }) => {
    await page.goto("/sign-up");
    await expect(page.getByText("Demo University")).toBeVisible();

    await assertNoCriticalAxeViolations(page);
  });

  test("has no critical axe violations on focused questions route", async ({ page }) => {
    await page.goto("/c/public-demo/questions?q=graphs&focus=chunk-1");
    await expect(page.getByRole("heading", { name: "2 matching questions" })).toBeVisible();
    await expect(page.getByRole("heading", { name: focusedChunk.text })).toBeVisible();

    await assertNoCriticalAxeViolations(page);
  });

  test("has no critical axe violations on answer route", async ({ page }) => {
    await page.goto("/c/public-demo/answer?q=graphs");
    await expect(page.getByText(studyResponse.answer.overview)).toBeVisible();
    await expect(page.getByText("Traversal invariant")).toBeVisible();

    await assertNoCriticalAxeViolations(page);
  });

  test("has no critical axe violations on source route", async ({ page }) => {
    await page.goto("/c/public-demo/source/chunk-1");
    await expect(page.getByText(focusedChunk.text)).toBeVisible();

    await assertNoCriticalAxeViolations(page);
  });
});
