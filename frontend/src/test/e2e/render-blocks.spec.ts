import { expect, test, type Page } from "@playwright/test";

import type {
  ChunkDetail,
  CollectionListItem,
  RenderBlock,
  SearchRequest,
  SearchResponse,
} from "@/lib/api/types";

const publicCollection: CollectionListItem = {
  name: "public-demo",
  display_name: "MIT 6.006 (demo)",
  community: null,
  paper_count: 12,
  year_range: { start: 2011, end: 2024 },
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

const renderedQuestionBlocks: RenderBlock[] = [
  {
    type: "paragraph",
    runs: [
      { type: "text", text: "Compute " },
      { type: "math", latex: "x^2" },
      { type: "text", text: " using the following helper." },
    ],
  },
  { type: "code", code: "def square(x):\n    return x * x", language: "python" },
  {
    type: "table",
    rows: [
      ["n", "cost"],
      ["1", "1"],
    ],
    media_id: null,
  },
];

const searchResponse: SearchResponse = {
  query: "render blocks",
  collection: "public-demo",
  total: 1,
  results: [
    {
      chunk_id: "chunk-render-blocks",
      chunk_level: "question",
      parent_chunk_id: null,
      sub_question_label: null,
      text: "Compute $x^2$ using code and <table> markup.",
      score: 0.94,
      metadata: {
        year: 2024,
        paper_label: "Quiz 2",
        question_label: "Question 3",
      },
      media: [],
      render_blocks: renderedQuestionBlocks,
    },
  ],
};

const chunkDetailResponse: ChunkDetail = {
  chunk_id: "chunk-render-blocks",
  chunk_level: "question",
  parent_chunk_id: null,
  sub_question_label: null,
  text: "Compute $x^2$ using code and <table> markup.",
  metadata: {
    year: 2024,
    paper_label: "Quiz 2",
    question_label: "Question 3",
  },
  media: [],
  collection: "public-demo",
  parent: null,
  render_blocks: renderedQuestionBlocks,
};

async function stubCollections(page: Page) {
  await page.route("**/collections", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([publicCollection]),
    });
  });
}

async function stubSearchAndChunkDetails(page: Page) {
  await stubCollections(page);

  await page.route("**/search", async (route) => {
    const request = route.request().postDataJSON() as SearchRequest;

    expect(request).toMatchObject({
      query: "render blocks",
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

  await page.route("**/collections/public-demo/chunks/chunk-render-blocks", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(chunkDetailResponse),
    });
  });
}

test("render_blocks round-trip renders structured search results", async ({ page }) => {
  await stubSearchAndChunkDetails(page);

  await page.goto("/c/public-demo/questions?q=render+blocks");

  await expect(page).toHaveURL(/\/c\/public-demo\/questions\?q=render\+blocks$/);
  await expect(page.getByRole("heading", { name: "1 matching question" })).toBeVisible();

  const resultRow = page.getByRole("button", { name: /Compute/ });
  await expect(resultRow.locator(".katex").first()).toBeVisible();
  await expect(resultRow.getByText("Contains code")).toBeVisible();
  await expect(resultRow.getByText("Contains table")).toBeVisible();

  await expect(page.getByText("$x^2$")).toBeHidden();
  await expect(page.getByText("<table>")).toBeHidden();
});
