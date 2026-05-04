import { expect, test, type Page } from "@playwright/test";

import type { CollectionListItem } from "@/lib/api/types";
import { LANDING_HERO_COPY } from "@/lib/publicCopy";

const collections: CollectionListItem[] = [
  {
    name: "public-demo",
    display_name: "Public Algorithms",
    community: null,
    paper_count: 12,
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
  },
  {
    name: "cam-cs-tripos",
    display_name: "Cambridge CS Tripos",
    community: { id: "cambridge", display_name: "Cambridge" },
    paper_count: 744,
    year_range: { start: 2018, end: 2025 },
    metadata_schema: {
      version: 1,
      fields: [
        {
          key: "paper",
          label: "Paper",
          type: "string",
          operators: ["eq"],
          exposed: true,
          source: "paper.label",
        },
      ],
    },
    access_state: "accessible",
    lock_reason: null,
  },
  {
    name: "locked-demo",
    display_name: "Locked University Archive",
    community: { id: "demo-university", display_name: "Demo University" },
    paper_count: 18,
    year_range: { start: 2019, end: 2025 },
    metadata_schema: null,
    access_state: "locked_requires_signin",
    lock_reason: "Sign in with Demo University email to unlock",
  },
];

const breakpoints = [
  { name: "mobile", width: 360, height: 720 },
  { name: "tablet", width: 768, height: 900 },
  { name: "desktop", width: 1280, height: 900 },
];

async function stubCollections(page: Page) {
  await page.route("**/collections", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(collections),
    });
  });
}

test.describe("landing responsive horizontal scroll", () => {
  for (const breakpoint of breakpoints) {
    test(`does not horizontally scroll at ${breakpoint.name} breakpoint`, async ({ page }) => {
      await stubCollections(page);
      await page.setViewportSize({
        width: breakpoint.width,
        height: breakpoint.height,
      });

      await page.goto("/");
      await expect(page.getByRole("heading", { name: LANDING_HERO_COPY.title })).toBeVisible();
      await expect(page.getByLabel("Query")).toBeVisible();
      await expect(page.getByText("Public Algorithms")).toBeVisible();

      const { scrollWidth, viewportWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
      }));

      expect(scrollWidth).toBeLessThanOrEqual(viewportWidth + 1);
    });
  }
});
