import { test, expect } from '@playwright/test'

test.describe('Review', () => {
  test('pending reviews page loads', async ({ page }) => {
    await page.goto('/review')

    // Page should show the review table or an empty state
    const table = page.getByRole('table')
    const emptyState = page.getByText(/no.*pending|no.*review|empty/i)
    const heading = page.getByText(/review/i)

    await expect(heading).toBeVisible()
    await expect(table.or(emptyState)).toBeVisible({ timeout: 10_000 })
  })

  test('approve finding with justification', async ({ page }) => {
    await page.goto('/review')

    // Check if there are pending findings to review
    const approveButton = page.getByRole('button', { name: /approve/i }).first()
    const emptyState = page.getByText(/no.*pending|no.*review/i)

    // If no pending reviews, skip gracefully
    const hasReviews = await approveButton.isVisible().catch(() => false)
    if (!hasReviews) {
      await expect(emptyState).toBeVisible()
      test.skip(true, 'No pending reviews available to test approval flow')
      return
    }

    // Click approve on the first finding
    await approveButton.click()

    // Fill justification (minimum 20 characters)
    const justificationInput = page.getByPlaceholder(/justification/i)
      .or(page.getByLabel(/justification|reason/i))
      .or(page.locator('textarea'))
    await justificationInput.fill(
      'Approved: this is a known test value used in integration testing environments only.'
    )

    // Confirm the approval
    const confirmButton = page.getByRole('button', { name: /confirm|submit/i })
    await confirmButton.click()

    // Verify success feedback
    await expect(
      page.getByText(/approved|success/i)
    ).toBeVisible({ timeout: 10_000 })
  })
})
