import { expect, test } from "@playwright/test";

import type {
  ChunkDetail,
  CollectionListItem,
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

const searchResponse: SearchResponse = {
  query: "dynamic programming",
  collection: "public-demo",
  total: 2,
  results: [
    {
      chunk_id: "chunk-1",
      chunk_level: "question",
      parent_chunk_id: null,
      sub_question_label: null,
      text: "Design a dynamic programming algorithm for optimal binary search trees.",
      score: 0.91,
      metadata: {
        year: 2024,
        paper_label: "Quiz 2",
        question_label: "Question 4",
      },
      media: [],
      render_blocks: null,
    },
    {
      chunk_id: "chunk-2",
      chunk_level: "question",
      parent_chunk_id: null,
      sub_question_label: null,
      text: "Use memoization to count paths in a directed acyclic graph.",
      score: 0.86,
      metadata: {
        year: 2023,
        paper_label: "Quiz 1",
        question_label: "Question 2",
      },
      media: [],
      render_blocks: null,
    },
  ],
};

const chunkDetailResponse: ChunkDetail = {
  chunk_id: "chunk-1",
  chunk_level: "question",
  parent_chunk_id: null,
  sub_question_label: null,
  text: "Full question: design a dynamic programming algorithm for optimal binary search trees and analyze its running time.",
  metadata: {
    year: 2024,
    paper_label: "Quiz 2",
    question_label: "Question 4",
  },
  media: [],
  collection: "public-demo",
  parent: null,
  render_blocks: null,
};

test("anonymous user can pick a public collection and search for matching questions", async ({
  page,
}) => {
  await page.route("**/collections", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([publicCollection]),
    });
  });

  await page.route("**/search", async (route) => {
    const request = route.request().postDataJSON() as SearchRequest;

    expect(request).toMatchObject({
      query: "dynamic programming",
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

  await page.route("**/collections/public-demo/chunks/chunk-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(chunkDetailResponse),
    });
  });

  await page.goto("/");

  await expect(page.getByText("Choose a collection below to enable search.")).toBeVisible();
  await expect(page.getByRole("link", { name: "View collections ↓" })).toHaveAttribute(
    "href",
    "#collections",
  );
  await page.getByRole("button", { name: /MIT 6\.006 \(demo\)/ }).click();

  await expect(page).toHaveURL(/\/c\/public-demo$/);
  await expect(
    page.getByRole("heading", { name: "Read the question. Then ask yours." }),
  ).toBeVisible();
  await expect(
    page.getByTestId("hero-action-row").getByRole("button", { name: "MIT 6.006 (demo)" }),
  ).toBeVisible();

  await page.getByLabel("Query").fill("dynamic programming");
  await page.getByRole("button", { name: "Find questions" }).click();

  await expect(page).toHaveURL(/\/c\/public-demo\/questions\?q=dynamic\+programming/);
  await expect(page.getByRole("heading", { name: "2 matching questions" })).toBeVisible();
  await expect(
    page.getByText("Design a dynamic programming algorithm for optimal binary search trees."),
  ).toBeVisible();
  await expect(
    page.getByText("Use memoization to count paths in a directed acyclic graph."),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Full question: design a dynamic programming algorithm for optimal binary search trees and analyze its running time.",
    }),
  ).toBeVisible();
});
