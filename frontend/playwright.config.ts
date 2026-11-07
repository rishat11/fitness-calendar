import { defineConfig, devices } from "@playwright/test";

// Отдельные порты, чтобы не задеть уже запущенные сайт и API разработчика.
const apiPort = "8010";
const webPort = "5174";

const backendEnv = {
  DATABASE_URL:
    process.env.DATABASE_URL ??
    "postgresql+asyncpg://fitness:fitness@127.0.0.1:5433/fitness",
  SECRET_KEY: process.env.SECRET_KEY ?? "local-e2e-secret-key-must-be-at-least-32-characters",
  COOKIE_SECURE: "false",
};

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? `http://127.0.0.1:${webPort}`,
    locale: "ru-RU",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: [
    {
      command: `uv run alembic upgrade head && uv run uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${apiPort}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: backendEnv,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${webPort}`,
      url: `http://127.0.0.1:${webPort}`,
      env: { API_PROXY_TARGET: `http://127.0.0.1:${apiPort}` },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
