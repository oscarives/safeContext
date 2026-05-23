import { test, expect } from '@playwright/test'

test.describe('Dashboard', () => {
  test('shows health cards and stats', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByText(/dashboard/i)).toBeVisible()

    // Verify the 4 health status cards are present
    const healthCards = ['Postgres', 'Redis', 'MinIO', 'Broker']
    for (const card of healthCards) {
      await expect(
        page.getByText(new RegExp(card, 'i'))
      ).toBeVisible({ timeout: 10_000 })
    }

    // Verify operations table or empty state is visible
    const table = page.getByRole('table')
    const emptyState = page.getByText(/no operations/i)
    await expect(table.or(emptyState)).toBeVisible({ timeout: 10_000 })
  })
})
