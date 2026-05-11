import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { resolvePlaywrightExecutablePath } from "./src/lib/playwright-browser";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../../..");
const executablePath = resolvePlaywrightExecutablePath();
const port = Number(process.env.PLAYWRIGHT_WEB_PORT ?? "8010");
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: {
    timeout: 120_000,
  },
  use: {
    baseURL,
    trace: "retain-on-failure",
    launchOptions: {
      executablePath,
    },
  },
  webServer: {
    command:
      `uv run --project libs/cli python -m uvicorn apps.webapp.api:app --app-dir . --host 127.0.0.1 --port ${port}`,
    cwd: repoRoot,
    url: `${baseURL}/api/health`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
