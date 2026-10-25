import { expect, test } from '@playwright/test'

import { apiPost, innOf, signIn } from './helpers'

test('a customer administrator sees only its licences and changes nothing', async ({ page, browser }) => {
  await signIn(page, '/users', 'admin')
  const stamp = String(Date.now())
  const name = `ООО «Просмотр ${stamp}»`
  const customer = await apiPost(page, '/api/admin/customers', { name, inn: innOf((Date.now() + 11) % 10_000_000) })
  const products = (await (await page.request.get('/api/admin/products')).json()) as {
    id: string
    code: string
    default_metric_id: string
  }[]
  const desktop = products.find((product) => product.code === 'alteroffice-desktop')
  await apiPost(page, '/api/admin/licenses', {
    customer_id: customer.id,
    product_id: desktop?.id,
    metric_id: desktop?.default_metric_id,
    type: 'subscription',
    limit: 3,
    valid_from: '2026-11-01T00:00:00Z',
    valid_until: '2027-10-31T20:59:59Z',
  })

  await page.reload()
  const username = `e2e-viewer-${stamp}`
  await page.getByTestId('user-create').click()
  await page.getByTestId('user-username').fill(username)
  await page.getByTestId('user-role').click()
  await page.getByRole('option', { name: 'Просмотр заказчика' }).click()
  await page.getByTestId('user-customer').click()
  await page.getByRole('option', { name }).filter({ visible: true }).click()
  await page.getByTestId('user-save').click()
  const password = (await page.getByTestId('issued-password').textContent()) ?? ''
  await page.getByTestId('issued-password-close').click()

  const viewer = await browser.newPage()
  await viewer.goto('/customers')
  await viewer.waitForLoadState('networkidle')
  await viewer.getByLabel('Логин').fill(username)
  await viewer.locator('#password').fill(password)
  await viewer.getByRole('button', { name: 'Войти' }).click()
  await expect(viewer.getByTestId('current-user')).toHaveText(username)
  await expect(viewer).toHaveURL(/\/licenses/)
  await expect(viewer.getByRole('menuitem', { name: 'Заказчики' })).toHaveCount(0)
  await expect(viewer.getByRole('menuitem', { name: 'Статистика' })).toHaveCount(1)

  const rows = viewer.getByTestId('licenses-table').locator('tbody tr')
  await expect(rows).toHaveCount(1)
  await expect(rows.first()).toContainText(name)
  await rows.first().getByTestId('license-open').click()
  await expect(viewer.getByRole('heading', { name })).toBeVisible()
  await expect(viewer.getByTestId('action-suspend')).toHaveCount(0)
  await viewer.close()
})
