import { expect, test } from '@playwright/test'

import { signIn } from './helpers'

const SAMPLE = '../server/tests/fixtures/lk-export-sample.xlsx'

test('an operator maps articles, confirms the import and a second import changes nothing', async ({ page }) => {
  await signIn(page, '/import')
  await page.getByTestId('import-file').setInputFiles(SAMPLE)
  await page.getByTestId('import-upload').click()
  await expect(page.getByTestId('import-summary')).toBeVisible()
  await expect(page.getByTestId('import-rows')).toContainText('****-****')
  await page.getByTestId('import-next').click()

  // AA 77 stays unmapped on purpose (an error row of the sample).
  await expect(page.getByTestId('mapping-77')).toBeVisible()
  for (const [aa, product] of [
    ['01', 'alteroffice-desktop'],
    ['02', 'alteroffice-web'],
  ] as const) {
    const row = page.getByTestId(`mapping-${aa}`)
    if ((await row.count()) === 0) continue
    await row.getByTestId('mapping-product').click()
    await page.getByRole('option', { name: product, exact: true }).filter({ visible: true }).first().click()
    await row.getByTestId('mapping-save').click()
    await expect(page.getByTestId(`mapping-saved-${aa}`)).toBeVisible()
  }
  await page.getByTestId('import-recheck').click()
  await expect(page.getByTestId('import-summary')).toBeVisible()
  await page.getByTestId('import-next').click()
  await page.getByRole('button', { name: 'Далее' }).click()
  await page.getByTestId('import-apply').click()
  await expect(page.getByTestId('import-report')).toBeVisible()

  await page.getByRole('button', { name: 'Импортировать другой файл' }).click()
  await page.getByTestId('import-file').setInputFiles(SAMPLE)
  await page.getByTestId('import-upload').click()
  await expect(page.getByTestId('summary-new')).toHaveText('Новые: 0')
  await expect(page.getByTestId('import-rows')).not.toContainText('TEST-ROWS')
})
