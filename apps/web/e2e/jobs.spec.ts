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

test("a lesson the user writes shows on Insights until they delete it", async ({ page }) => {
  const lesson = "No jobs that need a security clearance";
  await page.goto("/insights");
  await page.getByRole("textbox", { name: "Your own lesson" }).fill(lesson);
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText(lesson)).toBeVisible();
  await expect(page.getByText("Written by you")).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: `Delete lesson: ${lesson}` }).click();
  await expect(page.getByText(lesson)).toHaveCount(0);
});
