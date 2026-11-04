import { defineConfig, devices } from "@playwright/test";

const backendPython =
  process.env.PLAYWRIGHT_PYTHON ??
  (process.platform === "win32"
    ? "backend/.venv/Scripts/python.exe"
    : "backend/.venv/bin/python");

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.js",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: `${backendPython} backend/tests/e2e_server.py`,
      url: "http://127.0.0.1:5000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
    {
      command: "npm run dev -- --host 127.0.0.1",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
