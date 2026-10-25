import { expect, test } from '@playwright/test'

import { apiPost, innOf, signIn } from './helpers'

test('an operator finds an event in the journal and exports it to CSV', async ({ page }) => {
  await signIn(page, '/audit')
  const name = `ООО «Журнал ${String(Date.now())}»`
  const customer = await apiPost(page, '/api/admin/customers', { name, inn: innOf((Date.now() + 23) % 10_000_000) })

  await page.getByTestId('audit-object-type').click()
  await page.getByRole('option', { name: 'Заказчик' }).click()
  await page.getByTestId('audit-action').fill('customer.created')
  await page.getByTestId('audit-search').click()
  const row = page.getByTestId('audit-table').locator('tbody tr', { hasText: String(customer.id) })
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('customer.created')

  const download = page.waitForEvent('download')
  await page.getByTestId('audit-export').click()
  const file = await download
  expect(file.suggestedFilename()).toBe('almi-audit.csv')
})
