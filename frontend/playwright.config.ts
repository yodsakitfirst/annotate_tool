import { defineConfig } from '@playwright/test'
import path from 'node:path'

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://127.0.0.1:8765', trace: 'retain-on-failure', browserName: 'chromium', channel: process.env.PLAYWRIGHT_CHANNEL ?? (process.platform === 'win32' ? 'msedge' : undefined) },
  webServer: process.env.PLAYWRIGHT_EXTERNAL_SERVER ? undefined : {
    command: process.platform === 'win32'
      ? '.venv\\Scripts\\python.exe -m uvicorn annotate_tool.api.main:app --host 127.0.0.1 --port 8765'
      : 'python -m uvicorn annotate_tool.api.main:app --host 127.0.0.1 --port 8765',
    cwd: path.resolve('..'),
    env: {
      ANNOTATE_TOOL_DATA_DIR: path.resolve(`test-results/e2e-data-${process.pid}`),
      ANNOTATE_TOOL_FRONTEND_DIST: path.resolve('dist'),
    },
    url: 'http://127.0.0.1:8765/api/v1/health',
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
