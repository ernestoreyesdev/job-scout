import { expect, test } from "@playwright/test";

import { JOB_TITLE } from "./test-user";

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
