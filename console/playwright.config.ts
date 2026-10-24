// End-to-end scenarios of the console against a real server and PostgreSQL (DATABASE_URL).
// e2e/global-setup.ts migrates the database and creates an operator with a per-run password.
import { defineConfig } from '@playwright/test'

const api = 'http://127.0.0.1:8001'

export default defineConfig({
  testDir: 'e2e',
  globalSetup: './e2e/global-setup.ts',
  timeout: 30_000,
  // One database and one server for all scenarios: run them one after another.
  workers: 1,
  fullyParallel: false,
  use: {
    baseURL: 'http://127.0.0.1:5174',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {},
  },
  webServer: [
    {
      command: 'uv run python manage.py runserver 127.0.0.1:8001 --noreload',
      cwd: '../server',
      url: `${api}/health`,
      env: { DJANGO_SETTINGS_MODULE: 'almi_license.settings.dev', DEPLOYMENT_MODE: 'central' },
      reuseExistingServer: false,
    },
    {
      command: 'npx vite --host 127.0.0.1 --port 5174 --strictPort',
      url: 'http://127.0.0.1:5174',
      env: { VITE_API_TARGET: api },
      reuseExistingServer: false,
    },
  ],
})
