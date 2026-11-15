import { defineConfig, devices } from "@playwright/test";

// Runs against a production build on port 3000, one of the local Supabase stack's allowed sign-in redirects.
export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: "http://127.0.0.1:3000", trace: "retain-on-failure" },
  webServer: { command: "npm run start -- --port 3000", url: "http://127.0.0.1:3000/login", reuseExistingServer: !process.env.CI },
  projects: [
    { name: "setup", testMatch: /setup\.ts/ },
    {
      name: "signed in",
      testMatch: /jobs\.spec\.ts/,
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/user.json" },
    },
    {
      name: "account",
      testMatch: /account\.spec\.ts/,
      dependencies: ["signed in"],
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/user.json" },
    },
  ],
});
