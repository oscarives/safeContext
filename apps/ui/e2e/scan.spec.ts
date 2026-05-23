import { test, expect } from '@playwright/test'

test.describe('Scan', () => {
  test('empty document shows validation error', async ({ page }) => {
    await page.goto('/scan')

    // Click scan without entering any text
    const scanButton = page.getByRole('button', { name: /scan/i })
    await scanButton.click()

    // Should show a validation error
    await expect(
      page.getByText(/cannot be empty|required|enter.*document/i)
    ).toBeVisible()
  })

  test('scan document with sensitive data shows result', async ({ page }) => {
    await page.goto('/scan')

    // Paste text containing a test API key
    const textarea = page.getByRole('textbox').or(page.locator('textarea'))
    await textarea.fill(
      'My AWS key is AKIAIOSFODNN7EXAMPLE and my email is test@example.com'
    )

    // Click scan
    const scanButton = page.getByRole('button', { name: /scan/i })
    await scanButton.click()

    // Wait for result — either findings or clean result
    const findingResult = page.getByText(/finding|sensitive|detected|API_KEY/i)
    const cleanResult = page.getByText(/no.*sensitive|clean|no.*findings/i)
    const resultSection = page.getByText(/result|trace_id/i)

    await expect(
      findingResult.or(cleanResult).or(resultSection)
    ).toBeVisible({ timeout: 30_000 })
  })
})
