import { expect, test } from "@playwright/test";

import { SEARCH_KEYWORDS } from "./test-user";

test("the account menu turns on daily emails and picks a search for them", async ({ page }) => {
  await page.goto("/tracker");

  await page.getByRole("button", { name: "Account" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Daily match emails" }).click();
  await expect(page.getByRole("menuitemcheckbox", { name: "Daily match emails" })).toBeChecked();
  await page.getByRole("menuitem", { name: "Choose searches…" }).click();
  const search = page.getByRole("checkbox", { name: new RegExp(SEARCH_KEYWORDS) });
  await expect(page.getByText("Pick at least one search to get daily emails.")).toBeVisible();
  await search.check();
  await expect(page.getByText("Pick at least one search to get daily emails.")).toHaveCount(0);

  await page.reload();
  await page.getByRole("button", { name: "Account" }).click();
  await expect(page.getByRole("menuitemcheckbox", { name: "Daily match emails" })).toBeChecked();
  await page.getByRole("menuitem", { name: "Choose searches…" }).click();
  await expect(page.getByRole("checkbox", { name: new RegExp(SEARCH_KEYWORDS) })).toBeChecked();
  await page.getByRole("button", { name: "Done" }).click();
});

test("the account menu switches the theme and signs out", async ({ page }) => {
  await page.goto("/tracker");

  await page.getByRole("button", { name: "Account" }).click();
  await page.getByRole("menuitemradio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.getByRole("menuitemradio", { name: "Light" }).click();
  await expect(page.locator("html")).not.toHaveClass(/dark/);

  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
});
