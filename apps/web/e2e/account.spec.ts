import { expect, test } from "@playwright/test";

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
