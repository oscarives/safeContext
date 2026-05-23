import { test, expect } from '@playwright/test'

test.describe('Audit', () => {
  test('audit page shows export with HMAC signature', async ({ page }) => {
    await page.goto('/audit')

    // Page should load with the audit heading
    await expect(page.getByText(/audit/i)).toBeVisible()

    // Check if there are audit entries to view
    const auditTable = page.getByRole('table')
    const emptyState = page.getByText(/no.*audit|no.*operations|empty/i)

    const hasEntries = await auditTable.isVisible().catch(() => false)
    if (!hasEntries) {
      await expect(emptyState).toBeVisible()
      test.skip(true, 'No audit entries available to test HMAC export')
      return
    }

    // Click on the first audit entry or export button
    const exportButton = page.getByRole('button', { name: /export|view|detail/i }).first()
    await exportButton.click()

    // Verify HMAC signature section is visible in the export
    await expect(
      page.getByText(/hmac|signature|integrity/i)
    ).toBeVisible({ timeout: 10_000 })
  })
})
