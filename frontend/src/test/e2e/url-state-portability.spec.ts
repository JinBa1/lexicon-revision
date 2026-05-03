import { expect, test, type Page } from "@playwright/test";

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

const algorithmsSearchResponse: SearchResponse = {
  query: "algorithms",
  collection: "public-demo",
  total: 2,
  results: [
    {
      chunk_id: "chunk-1",
      chunk_level: "question",
      parent_chunk_id: null,
      sub_question_label: null,
      text: "Analyze the running time of a divide-and-conquer sorting algorithm.",
      score: 0.92,
      metadata: {
        year: 2024,
        paper_label: "Quiz 2",
        question_label: "Question 1",
      },
      media: [],
      render_blocks: null,
    },
    {
      chunk_id: "chunk-2",
      chunk_level: "question",
      parent_chunk_id: null,
      sub_question_label: null,
      text: "Explain how graph search algorithms recover shortest paths.",
      score: 0.88,
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

const chunkDetails: Record<string, ChunkDetail> = {
  "chunk-1": {
    chunk_id: "chunk-1",
    chunk_level: "question",
    parent_chunk_id: null,
    sub_question_label: null,
    text: "Full chunk-1 detail: analyze the running time of divide-and-conquer sorting.",
    metadata: {
      year: 2024,
      paper_label: "Quiz 2",
      question_label: "Question 1",
    },
    media: [],
    collection: "public-demo",
    parent: null,
    render_blocks: null,
  },
  "chunk-2": {
    chunk_id: "chunk-2",
    chunk_level: "question",
    parent_chunk_id: null,
    sub_question_label: null,
    text: "Full chunk-2 detail: graph search algorithms recover shortest paths with predecessor links.",
    metadata: {
      year: 2023,
      paper_label: "Quiz 1",
      question_label: "Question 2",
    },
    media: [],
    collection: "public-demo",
    parent: null,
    render_blocks: null,
  },
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
      query: "algorithms",
      collection: "public-demo",
      filters: [],
      limit: 15,
      rerank: true,
    });

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(algorithmsSearchResponse),
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

async function expectAlgorithmsResults(page: Page) {
  await expect(page.getByRole("heading", { name: "Top 2 results" })).toBeVisible();
  await expect(
    page.getByText("Analyze the running time of a divide-and-conquer sorting algorithm."),
  ).toBeVisible();
  await expect(
    page.getByText("Explain how graph search algorithms recover shortest paths."),
  ).toBeVisible();
}

test("same URL restores identical questions view in a new page", async ({ context, page }) => {
  await stubSearchAndChunkDetails(page);

  await page.goto("/c/public-demo/questions?q=algorithms");
  await expect(page).toHaveURL(/\/c\/public-demo\/questions\?q=algorithms$/);
  await expectAlgorithmsResults(page);

  const restoredUrl = page.url();
  const second = await context.newPage();
  await stubSearchAndChunkDetails(second);

  await second.goto(restoredUrl);
  await expect(second).toHaveURL(restoredUrl);
  await expectAlgorithmsResults(second);
});

test("focus param deep-links the selected chunk detail state", async ({ page }) => {
  await stubSearchAndChunkDetails(page);

  await page.goto("/c/public-demo/questions?q=algorithms&focus=chunk-2");

  await expect(page).toHaveURL(/\/c\/public-demo\/questions\?q=algorithms&focus=chunk-2$/);
  await expectAlgorithmsResults(page);
  await expect(
    page
      .getByRole("article")
      .first()
      .getByText(
        "Full chunk-2 detail: graph search algorithms recover shortest paths with predecessor links.",
      ),
  ).toBeVisible();
});

test("broken filter URL renders invalid state with clear filters action", async ({ page }) => {
  let searchRequests = 0;
  await stubCollections(page);
  await page.route("**/search", async (route) => {
    searchRequests += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(algorithmsSearchResponse),
    });
  });

  await page.goto("/c/public-demo/questions?q=algorithms&filter=section%3Ain%3Abroken");

  await expect(page.getByText("Filters in this link aren't valid")).toBeVisible();
  await expect(page.getByText("Adjust or clear filters to continue.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clear filters" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Top 2 results" })).toBeHidden();
  await expect(
    page.getByText("Analyze the running time of a divide-and-conquer sorting algorithm."),
  ).toBeHidden();
  expect(searchRequests).toBe(0);

  await page.getByRole("button", { name: "Clear filters" }).click();

  await expect(page).toHaveURL(/\/c\/public-demo\/questions\?q=algorithms$/);
  await expectAlgorithmsResults(page);
  expect(searchRequests).toBe(1);
});

test("collection-home filters stay open and remain draft-only until explicit search", async ({
  page,
}) => {
  let searchRequests = 0;
  await stubCollections(page);
  await page.route("**/search", async (route) => {
    searchRequests += 1;
    const request = route.request().postDataJSON() as SearchRequest;

    expect(request).toMatchObject({
      query: "algorithms",
      collection: "public-demo",
      filters: [{ field: "year", op: "gte", value: 2021 }],
      limit: 15,
      rerank: true,
    });

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(algorithmsSearchResponse),
    });
  });

  await page.goto("/c/public-demo?q=algorithms");

  const filtersButton = page.getByRole("button", { name: "Filters" });
  await filtersButton.click();

  await expect(page.getByRole("dialog", { name: "Filters" })).toBeVisible();
  await expect(filtersButton).toHaveAttribute("aria-expanded", "true");

  await page.getByLabel("Year from").fill("2021");

  await expect(page.getByRole("button", { name: "Filters (1)" })).toBeVisible();
  await expect(page).toHaveURL(/\/c\/public-demo\?q=algorithms$/);
  expect(searchRequests).toBe(0);

  await page.getByRole("button", { name: "Find questions" }).click();

  await expect(page).toHaveURL(
    /\/c\/public-demo\/questions\?q=algorithms&filter=year%3Agte%3A2021$/,
  );
  await expectAlgorithmsResults(page);
  expect(searchRequests).toBe(1);
});
