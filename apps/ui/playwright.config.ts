import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E configuration for SafeContext UI.
 *
 * Usage:
 *   npx playwright test              → run all E2E tests (requires backend)
 *   npx playwright test --list       → list tests without running
 *   npx playwright test --ui         → interactive UI mode
 *
 * Prerequisites:
 *   docker compose --profile auth up → full stack with Keycloak
 *   E2E_USER / E2E_PASSWORD env vars → test realm credentials (defaults: testuser/testpassword)
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'html',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'e2e/.auth/user.json',
      },
      dependencies: ['setup'],
    },
  ],
  webServer: process.env.CI
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://localhost:3000',
        reuseExistingServer: true,
      },
})
