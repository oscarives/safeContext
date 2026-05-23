import { test, expect } from '@playwright/test'

test.describe('Authentication', () => {
  test('login redirects to dashboard', async ({ page }) => {
    await page.goto('/dashboard')

    // Storage state from setup — user should be authenticated
    await expect(page).toHaveURL(/.*dashboard/)
    await expect(page.getByText(/dashboard/i)).toBeVisible()

    // Username badge should be visible in the header/nav
    await expect(page.getByTestId('user-badge').or(page.getByRole('button', { name: /user|profile|account/i }))).toBeVisible()
  })

  test('logout clears session', async ({ page, context }) => {
    await page.goto('/dashboard')
    await expect(page.getByText(/dashboard/i)).toBeVisible()

    // Click logout
    const logoutButton = page.getByRole('button', { name: /logout|sign out/i })
      .or(page.getByTestId('logout-button'))
    await logoutButton.click()

    // Should redirect to login page
    await page.waitForURL(/.*login/)
    await expect(page).toHaveURL(/.*login/)

    // Attempting to access protected page should redirect to login
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/.*login/)
  })
})
