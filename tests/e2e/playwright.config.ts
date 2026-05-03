import { defineConfig, devices } from "@playwright/test";
import path from "path";

const ROOT = path.resolve(__dirname, "../..");
const BACKEND_PORT = 8084;
const FRONTEND_PORT = 5181;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 1,
  workers: 1,
  reporter: "list",
  timeout: 30_000,
  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      // always start fresh so STUB_PROVIDERS is guaranteed
      command: `STUB_PROVIDERS=true DATABASE_URL="sqlite+aiosqlite:///${ROOT}/data/e2e_test.db" UPLOADS_DIR="${ROOT}/uploads" GENERATED_DIR="${ROOT}/generated" python3 -m uvicorn backend.main:app --host 127.0.0.1 --port ${BACKEND_PORT}`,
      url: `http://127.0.0.1:${BACKEND_PORT}/api/chats`,
      cwd: ROOT,
      reuseExistingServer: false,
      timeout: 20_000,
    },
    {
      command: `cd ${ROOT}/frontend && BACKEND_PORT=${BACKEND_PORT} npm run dev -- --port ${FRONTEND_PORT} --strictPort`,
      url: `http://localhost:${FRONTEND_PORT}`,
      reuseExistingServer: false,
      timeout: 20_000,
    },
  ],
});
