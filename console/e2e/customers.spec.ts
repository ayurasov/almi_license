import { expect, test } from '@playwright/test'

import { innOf, signIn } from './helpers'

test('an operator creates a customer and finds it with a filter', async ({ page }) => {
  const name = `ООО «Тест ${String(Date.now())}»`
  const inn = innOf(Date.now() % 10_000_000)

  await signIn(page, '/customers')

  await page.getByTestId('customer-create').click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Наименование').fill(name)
  await dialog.getByLabel('ИНН').fill(inn)
  await dialog.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.getByText('Заказчик сохранён')).toBeVisible()

  await page.getByTestId('filter-inn').fill(inn)
  await page.getByTestId('filter-apply').click()
  await expect(page).toHaveURL(new RegExp(`inn=${inn}`))
  const rows = page.getByTestId('customers-table').locator('tbody tr')
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText(name)
})
