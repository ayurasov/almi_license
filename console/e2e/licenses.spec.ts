import { expect, test } from '@playwright/test'

import { apiPost, innOf, signIn } from './helpers'

test('an operator issues a key and suspends a license with a reason', async ({ page }) => {
  await signIn(page, '/licenses')
  const products = (await (await page.request.get('/api/admin/products')).json()) as {
    id: string
    code: string
    default_metric_id: string
  }[]
  const desktop = products.find((product) => product.code === 'alteroffice-desktop')
  expect(desktop).toBeDefined()
  const name = `ООО «Лицензия ${String(Date.now())}»`
  const customer = await apiPost(page, '/api/admin/customers', { name, inn: innOf((Date.now() + 7) % 10_000_000) })
  await apiPost(page, '/api/admin/licenses', {
    customer_id: customer.id,
    product_id: desktop?.id,
    metric_id: desktop?.default_metric_id,
    type: 'subscription',
    limit: 10,
    valid_from: '2026-11-01T00:00:00Z',
    valid_until: '2027-10-31T20:59:59Z',
  })

  await page.reload()
  const row = page.getByTestId('licenses-table').locator('tbody tr', { hasText: name })
  await expect(row).toHaveCount(1)
  await row.getByTestId('license-open').click()
  await expect(page.getByRole('heading', { name })).toBeVisible()

  await page.getByRole('tab', { name: 'Ключи' }).click()
  await page.getByTestId('issue-key').click()
  const key = await page.getByTestId('issued-key').textContent()
  expect(key).toMatch(/^\d{4}-[0-9A-HJ-NP-Z]{4}-[0-9A-HJ-NP-Z]{4}-[0-9A-HJ-NP-Z]{4}$/)
  await page.getByTestId('issued-key-close').click()
  await expect(page.getByText(`${key?.slice(0, 4) ?? ''}-****-****-${key?.slice(-4) ?? ''}`)).toBeVisible()
  await expect(page.getByText(key ?? 'none')).toHaveCount(0)

  await page.getByTestId('action-settings').click()
  await page.getByTestId('action-user-limit').locator('input').fill('500')
  await page.getByLabel('Считать только активных пользователей').check()
  await page.getByTestId('action-confirm').click()
  await page.getByRole('tab', { name: 'Параметры' }).click()
  await expect(page.getByTestId('user-limit')).toHaveText('500 (только активные)')

  await page.getByTestId('action-suspend').click()
  await page.getByTestId('action-confirm').click()
  await expect(page.getByText('Укажите причину.')).toBeVisible()
  await page.getByLabel('Причина').fill('Неоплата счёта')
  await page.getByTestId('action-confirm').click()
  await expect(page.getByTestId('license-status')).toHaveText('Приостановлена')

  await page.getByRole('tab', { name: 'История' }).click()
  await expect(page.getByText('license.suspended')).toBeVisible()
})
