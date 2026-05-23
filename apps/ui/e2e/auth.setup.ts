import { test as setup, expect } from '@playwright/test'

const E2E_USER = process.env.E2E_USER || 'testuser'
const E2E_PASSWORD = process.env.E2E_PASSWORD || 'testpassword'
const AUTH_FILE = 'e2e/.auth/user.json'

/**
 * Authentication setup — runs once before all tests.
 *
 * Logs in via Keycloak SSO and persists the browser storage state
 * so subsequent tests reuse the authenticated session without
 * repeating the login flow.
 */
setup('authenticate via Keycloak SSO', async ({ page }) => {
  // Navigate to login page
  await page.goto('/login')

  // Click SSO login button
  await page.getByRole('button', { name: /sign in with sso/i }).click()

  // Wait for Keycloak login form
  await page.waitForURL(/.*keycloak.*/)

  // Fill Keycloak credentials
  await page.getByLabel(/username/i).fill(E2E_USER)
  await page.getByLabel(/password/i).fill(E2E_PASSWORD)
  await page.getByRole('button', { name: /sign in|log in/i }).click()

  // Wait for redirect back to dashboard
  await page.waitForURL('**/dashboard')
  await expect(page.getByText(/dashboard/i)).toBeVisible()

  // Save authenticated state
  await page.context().storageState({ path: AUTH_FILE })
})
