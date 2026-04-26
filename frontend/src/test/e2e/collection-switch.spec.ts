import { expect, test, type Page } from "@playwright/test";

import type {
  ChunkDetail,
  CollectionListItem,
  SearchRequest,
  SearchResponse,
  SupportedUniversity,
} from "@/lib/api/types";

const publicCollection: CollectionListItem = {
  name: "public-demo",
  display_name: "Public Demo",
  community: null,
  paper_count: 12,
  year_range: { start: 2019, end: 2025 },
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

const openArchiveCollection: CollectionListItem = {
  name: "open-archive",
  display_name: "Open Archive",
  community: null,
  paper_count: 9,
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

const lockedCollection: CollectionListItem = {
  name: "locked-demo",
  display_name: "Locked Demo",
  community: { id: "demo-university", display_name: "Demo University" },
  paper_count: 18,
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

const collections = [publicCollection, openArchiveCollection, lockedCollection];

function searchResponseFor(request: SearchRequest): SearchResponse {
  return {
    query: request.query,
    collection: request.collection,
    total: 1,
    results: [
      {
        chunk_id: `${request.collection}-chunk-1`,
        chunk_level: "question",
        parent_chunk_id: null,
        sub_question_label: null,
        text: `Question result for ${request.collection}`,
        score: 0.91,
        metadata: {
          year: 2022,
          paper_label: "Mock Paper",
          question_label: "Question 1",
        },
        media: [],
        render_blocks: null,
      },
    ],
  };
}

function chunkDetailFor(collection: string, chunkId: string): ChunkDetail {
  return {
    chunk_id: chunkId,
    chunk_level: "question",
    parent_chunk_id: null,
    sub_question_label: null,
    text: `Full question detail for ${collection}`,
    metadata: {
      year: 2022,
      paper_label: "Mock Paper",
      question_label: "Question 1",
    },
    media: [],
    collection,
    parent: null,
    render_blocks: null,
  };
}

async function stubFrontendContract(page: Page, onSearch?: (request: SearchRequest) => void) {
  await page.route("**/collections", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(collections),
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
    onSearch?.(request);

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(searchResponseFor(request)),
    });
  });

  await page.route("**/collections/*/chunks/*", async (route) => {
    const url = new URL(route.request().url());
    const [, collection, chunkId] =
      url.pathname.match(/\/collections\/([^/]+)\/chunks\/([^/]+)/) ?? [];

    await route.fulfill({
      status: collection && chunkId ? 200 : 404,
      contentType: "application/json",
      body: JSON.stringify(
        collection && chunkId
          ? chunkDetailFor(decodeURIComponent(collection), decodeURIComponent(chunkId))
          : { detail: "Not found" },
      ),
    });
  });
}

test("switching accessible collections preserves query on home and clears filters", async ({
  page,
}) => {
  const searchRequests: SearchRequest[] = [];
  await stubFrontendContract(page, (request) => searchRequests.push(request));

  await page.goto("/c/public-demo/questions?q=x&filter=year%3Aeq%3A2022");

  await expect(page).toHaveURL(/\/c\/public-demo\/questions\?q=x&filter=year%3Aeq%3A2022$/);
  await expect(page.getByText("1 question matches")).toBeVisible();
  expect(searchRequests).toContainEqual(
    expect.objectContaining({
      query: "x",
      collection: "public-demo",
      filters: [{ field: "year", op: "eq", value: 2022 }],
    }),
  );
  const requestCountBeforeScopeSelection = searchRequests.length;

  await page.getByRole("button", { name: "Public Demo ▾" }).click();
  await expect(page).toHaveURL("/?scopePicker=1&page=questions&q=x");

  await page.getByRole("button", { name: "Open Archive" }).click();

  await expect(page).toHaveURL(/\/c\/open-archive\?q=x$/);
  await expect(page).not.toHaveURL(/filter=/);
  await expect(page.getByRole("heading", { level: 1, name: "Open Archive" })).toBeVisible();
  expect(searchRequests).toHaveLength(requestCountBeforeScopeSelection);
  expect(searchRequests).not.toContainEqual(
    expect.objectContaining({ collection: "open-archive" }),
  );
});

test("switching to a sign-in locked collection routes anonymous users to unlock with return target", async ({
  page,
}) => {
  await stubFrontendContract(page);

  await page.goto("/c/public-demo/questions?q=x");
  await expect(page.getByText("1 question matches")).toBeVisible();

  await page.getByRole("button", { name: "Public Demo ▾" }).click();
  await expect(page).toHaveURL("/?scopePicker=1&page=questions&q=x");

  await page
    .getByRole("button", {
      name: /Locked Demo\. Locked\. Sign in with Demo University email to unlock/,
    })
    .click();

  await expect(page).toHaveURL("/unlock/locked-demo?returnTo=%2Fc%2Flocked-demo%3Fq%3Dx");
});
