import { expect, test, type Page } from "@playwright/test";

import type { CollectionListItem, SupportedUniversity } from "@/lib/api/types";

const cambridgeLocked: CollectionListItem = {
  name: "cam-cs-tripos",
  display_name: "Cambridge CS Tripos",
  community: { id: "cambridge", display_name: "Cambridge" },
  paper_count: 744,
  year_range: { start: 2018, end: 2025 },
  metadata_schema: null,
  access_state: "locked_requires_signin",
  lock_reason: "Sign in with Cambridge email to unlock",
};

const oxfordWrongAffiliation: CollectionListItem = {
  name: "ox-maths",
  display_name: "Oxford Mathematics",
  community: { id: "oxford", display_name: "Oxford" },
  paper_count: 310,
  year_range: { start: 2019, end: 2025 },
  metadata_schema: null,
  access_state: "locked_wrong_affiliation",
  lock_reason: "Unavailable to your signed-in account",
};

const supportedUniversities: SupportedUniversity[] = [
  {
    id: "cambridge",
    display_name: "Cambridge",
    email_domains: ["cam.ac.uk"],
  },
  {
    id: "oxford",
    display_name: "Oxford",
    email_domains: ["ox.ac.uk"],
  },
];

async function stubCatalogue(page: Page, collections: CollectionListItem[]) {
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
}

test("anonymous user clicks a locked card and reaches the unlock signup bridge", async ({
  page,
}) => {
  await stubCatalogue(page, [cambridgeLocked]);

  await page.goto("/");
  await page
    .getByRole("button", {
      name: /Cambridge CS Tripos\. Locked\. Sign in with Cambridge email to unlock/,
    })
    .click();

  await expect(page).toHaveURL(/\/unlock\/cam-cs-tripos\?returnTo=%2Fc%2Fcam-cs-tripos$/);
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Cambridge CS Tripos is restricted to Cambridge members.",
    }),
  ).toBeVisible();
  await expect(page.getByText("Use your @cam.ac.uk email to sign up.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign up with cam.ac.uk email" })).toHaveAttribute(
    "href",
    "/sign-up?university=cambridge&returnTo=%2Fc%2Fcam-cs-tripos",
  );
  await expect(page.getByRole("link", { name: "Sign in to an existing account" })).toHaveAttribute(
    "href",
    "/sign-in?returnTo=%2Fc%2Fcam-cs-tripos",
  );
});

test("signed-in wrong-affiliation user stays on the catalogue and sees the locked explanation", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.sessionStorage.setItem("rag_exam.stub_header_email", "student@cam.ac.uk");
  });
  await stubCatalogue(page, [oxfordWrongAffiliation]);

  await page.goto("/");
  await page
    .getByRole("button", {
      name: /Oxford Mathematics\. Locked\. Unavailable to your signed-in account/,
    })
    .click();

  await expect(page).toHaveURL("/");
  await expect(
    page.getByRole("dialog", { name: "Oxford Mathematics access mismatch" }),
  ).toBeVisible();
  const dialog = page.getByRole("dialog", { name: "Oxford Mathematics access mismatch" });
  await expect(
    dialog.getByText(
      "Your signed-in account does not currently match the affiliation required for Oxford Mathematics.",
    ),
  ).toBeVisible();
  await expect(dialog.getByText("Unavailable to your signed-in account")).toBeVisible();
});
