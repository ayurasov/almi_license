import { expect, test } from '@playwright/test'

import { signIn } from './helpers'

test('an administrator creates a user, blocks and resets the password', async ({ page, browser }) => {
  await signIn(page, '/users', 'admin')
  const username = `e2e-user-${String(Date.now())}`
  await page.getByTestId('user-create').click()
  await page.getByTestId('user-username').fill('Bad Name')
  await page.getByTestId('user-save').click()
  await expect(page.getByText('Латиница в нижнем регистре, цифры, точка, дефис, _; 2–64 символа.')).toBeVisible()
  await page.getByTestId('user-username').fill(username)
  await page.getByTestId('user-save').click()
  const first = (await page.getByTestId('issued-password').textContent()) ?? ''
  expect(first).toMatch(/^[A-Za-z2-9]{20}$/)
  await page.getByTestId('issued-password-close').click()
  await expect(page.getByText(first)).toHaveCount(0)

  // The new operator signs in with the issued password and does not see the Users section.
  const other = await browser.newPage()
  await other.goto('/customers')
  await other.waitForLoadState('networkidle')
  await other.getByLabel('Логин').fill(username)
  await other.locator('#password').fill(first)
  await other.getByRole('button', { name: 'Войти' }).click()
  await expect(other.getByTestId('current-user')).toHaveText(username)
  await expect(other.getByRole('menuitem', { name: 'Пользователи' })).toHaveCount(0)

  const row = page.getByTestId('users-table').locator('tbody tr', { hasText: username })
  await row.getByTestId('user-block').click()
  await page.getByTestId('user-confirm').click()
  await expect(row.getByText('Заблокирован')).toBeVisible()
  await other.reload()
  await expect(other).toHaveURL(/\/login/)

  await row.getByTestId('user-unblock').click()
  await row.getByTestId('user-reset').click()
  await page.getByTestId('user-confirm').click()
  const second = (await page.getByTestId('issued-password').textContent()) ?? ''
  expect(second).not.toBe(first)
  await page.getByTestId('issued-password-close').click()
  await other.close()
})
