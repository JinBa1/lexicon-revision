import { defineConfig, devices } from "@playwright/test";

const e2eViteEnv = {
  ...process.env,
  VITE_API_BASE_URL: "http://localhost:8000",
  VITE_AUTH_MODE: "stub_header",
  VITE_STUB_AUTH_EMAIL: "",
  VITE_CLERK_PUBLISHABLE_KEY: "pk_test_REPLACE_ME",
  VITE_BUILD_SHA: "e2e",
};

export default defineConfig({
  testDir: "./src/test/e2e",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: "corepack pnpm exec vite --host 127.0.0.1 --port 4173 --strictPort",
        env: e2eViteEnv,
        url: "http://127.0.0.1:4173",
        reuseExistingServer: true,
        timeout: 60_000,
      },
});
