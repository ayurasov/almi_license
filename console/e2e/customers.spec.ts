import { expect, test } from '@playwright/test'

// INN with a valid check digit, unique per run (the server keeps INN unique).
function innOf(seed: number): string {
  const weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
  const body = `77${String(seed).padStart(7, '0').slice(-7)}`
  const sum = weights.reduce((total, weight, i) => total + Number(body.charAt(i)) * weight, 0)
  return body + String((sum % 11) % 10)
}

test('an operator creates a customer and finds it with a filter', async ({ page }) => {
  const name = `ООО «Тест ${String(Date.now())}»`
  const inn = innOf(Date.now() % 10_000_000)

  await page.goto('/customers')
  await expect(page).toHaveURL(/\/login/)
  await page.getByLabel('Логин').fill(process.env.E2E_USERNAME ?? '')
  await page.locator('#password').fill(process.env.E2E_PASSWORD ?? '')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByTestId('current-user')).toHaveText(process.env.E2E_USERNAME ?? '')

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
