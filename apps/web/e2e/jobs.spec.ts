import { expect, test } from "@playwright/test";

import { JOB_TITLE, RATED_TITLE } from "./test-user";

test("the tracker lists the user's new job", async ({ page }) => {
  await page.goto("/tracker");

  await expect(page.getByRole("link", { name: JOB_TITLE })).toBeVisible();
});

test("a status change moves the job to Jobs and survives a reload", async ({ page }) => {
  await page.goto("/tracker");
  const row = page.getByRole("link", { name: JOB_TITLE }).locator("xpath=ancestor::*[.//button[@role='combobox']][1]");
  await row.getByRole("combobox").click();
  await page.getByRole("option", { name: "Saved" }).click();
  await expect(page.getByRole("link", { name: JOB_TITLE })).toHaveCount(0);

  await page.goto("/jobs");
  await page.reload();
  const saved = page.getByRole("link", { name: JOB_TITLE }).locator("xpath=ancestor::*[.//button[@role='combobox']][1]");
  await expect(saved.getByRole("combobox")).toHaveText(/saved/i);
});

test("a good rating saves the job to Jobs and keeps it under Rated", async ({ page }) => {
  await page.goto("/tracker");
  await page.getByRole("button", { name: `Mark ${RATED_TITLE} as a good fit` }).click();
  await expect(page.getByRole("link", { name: RATED_TITLE })).toHaveCount(0);

  await page.goto("/jobs");
  const saved = page.getByRole("link", { name: RATED_TITLE }).locator("xpath=ancestor::*[.//button[@role='combobox']][1]");
  await expect(saved.getByRole("combobox")).toHaveText(/saved/i);

  await page.goto("/tracker?view=rated");
  await expect(page.getByRole("link", { name: RATED_TITLE })).toBeVisible();
});
