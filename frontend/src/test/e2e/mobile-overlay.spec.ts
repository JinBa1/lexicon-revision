import { expect, test } from "@playwright/test";

import type { ChunkDetail, CollectionListItem, SearchResponse } from "@/lib/api/types";

test.use({ viewport: { width: 375, height: 812 } });

test("mobile overlay opens on row click and closes via back button", async ({ page }) => {
  const collection: CollectionListItem = {
    name: "cam",
    display_name: "Cambridge Demo",
    community: null,
    paper_count: 10,
    year_range: { start: 2020, end: 2025 },
    metadata_schema: null,
    access_state: "accessible",
    lock_reason: null,
  };

  const searchResponse: SearchResponse = {
    query: "smoke",
    collection: "cam",
    results: [
      {
        chunk_id: "smoke-1",
        chunk_level: "question",
        parent_chunk_id: null,
        sub_question_label: null,
        text: "first result body",
        score: 0.9,
        metadata: {},
        media: [],
        render_blocks: null,
      },
    ],
    total: 1,
  };

  const chunkDetail: ChunkDetail = {
    chunk_id: "smoke-1",
    chunk_level: "question",
    parent_chunk_id: null,
    sub_question_label: null,
    text: "first result body",
    metadata: {},
    media: [],
    collection: "cam",
    parent: null,
    render_blocks: null,
  };

  await page.route("**/collections", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([collection]),
    });
  });

  await page.route("**/search", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(searchResponse),
    });
  });

  await page.route("**/collections/cam/chunks/smoke-1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(chunkDetail),
    });
  });

  await page.goto("/c/cam/questions?q=smoke");
  await page.getByRole("button", { name: /first result body/i }).click();
  const back = page.getByRole("button", { name: /back to results/i });
  await expect(back).toBeVisible();
  await back.click();
  await expect(back).not.toBeVisible();
});
