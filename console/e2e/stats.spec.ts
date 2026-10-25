import { expect, test } from '@playwright/test'

import { signIn } from './helpers'

test('an operator sees the statistics and exports them to XLSX', async ({ page }) => {
  await signIn(page, '/stats')
  await expect(page.getByTestId('stats-tiles')).toBeVisible()
  await expect(page.getByTestId('tile-licenses')).toContainText('Лицензий')
  const download = page.waitForEvent('download')
  await page.getByTestId('stats-export').click()
  const file = await download
  expect(file.suggestedFilename()).toBe('almi-stats.xlsx')
})
