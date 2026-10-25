import { expect, test } from '@playwright/test'

import { apiPost, innOf, signIn } from './helpers'

test('an operator creates a local server with seats and gets a one-time code', async ({ page }) => {
  await signIn(page, '/servers')
  const products = (await (await page.request.get('/api/admin/products')).json()) as {
    id: string
    code: string
    default_metric_id: string
  }[]
  const desktop = products.find((product) => product.code === 'alteroffice-desktop')
  const name = `ООО «Сервер ${String(Date.now())}»`
  const customer = await apiPost(page, '/api/admin/customers', { name, inn: innOf((Date.now() + 11) % 10_000_000) })
  await apiPost(page, '/api/admin/licenses', {
    customer_id: customer.id,
    product_id: desktop?.id,
    metric_id: desktop?.default_metric_id,
    type: 'subscription',
    limit: 10,
    valid_from: '2026-11-01T00:00:00Z',
    valid_until: '2027-10-31T20:59:59Z',
  })

  await page.getByTestId('server-create').click()
  await page.getByTestId('server-customer').click()
  await page.getByRole('option', { name }).click()
  await page.getByTestId('server-name').fill('ЦОД заказчика')
  await page.getByTestId('server-seats').locator('input').fill('4')
  await page.getByTestId('server-save').click()

  const code = (await page.getByTestId('registration-code').textContent()) ?? ''
  expect(code).toMatch(/^[A-Z2-9]{5}(-[A-Z2-9]{5}){3}$/)
  await page.getByTestId('registration-code-close').click()
  await expect(page.getByText(code)).toHaveCount(0)
  const row = page.getByTestId('servers-table').locator('tbody tr', { hasText: 'ЦОД заказчика' }).first()
  await expect(row).toContainText('Ожидает регистрации')
  await expect(row).toContainText('4')
})
