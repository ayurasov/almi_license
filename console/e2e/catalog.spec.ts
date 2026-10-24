import { expect, test } from '@playwright/test'

import { signIn } from './helpers'

test('an operator adds a capability and saves a profile version with a message', async ({ page }) => {
  await signIn(page, '/catalog')
  const capability = `e2e_${String(Date.now())}`
  await page.getByTestId('products-table').locator('tbody tr', { hasText: 'alteroffice-desktop' }).click()
  await expect(page.getByTestId('product-details')).toBeVisible()
  await page.getByTestId('capability-code').fill('Bad Code')
  await page.getByTestId('capability-add').click()
  await expect(page.getByText('Код функции: латиница, цифры и _, или app:<имя>.')).toBeVisible()
  await page.getByTestId('capability-code').fill(capability)
  await page.getByTestId('capability-add').click()
  await expect(page.getByTestId('capabilities-table').getByText(capability)).toBeVisible()

  await page.goto('/profiles')
  await page.getByTestId('profiles-table').locator('tbody tr', { hasText: 'alteroffice-desktop.commercial' }).click()
  const editor = page.getByTestId('profile-editor')
  await expect(editor).toBeVisible()
  const history = page.getByTestId('profile-history').locator('tbody tr')
  await expect(history.first()).not.toHaveText(/^$/)
  const before = Number(await history.first().locator('td').first().textContent())
  expect(before).toBeGreaterThan(0)

  await page.getByTestId('profile-grace_days').locator('input').fill('400')
  await page.getByTestId('profile-save').click()
  await expect(editor.getByText('Целое от 0 до 365.')).toBeVisible()

  await page.getByTestId('profile-grace_days').locator('input').fill(String(15 + (before % 100)))
  await page.getByTestId('message-add').click()
  const message = page.getByTestId(/^message-\d+$/).last()
  await message.getByTestId('message-id').fill('grace.banner')
  await message.getByTestId('message-ru').fill('Осталось {days_left}, {days}')
  await expect(message.getByTestId('message-preview')).toContainText('Осталось 7, {days}')
  await expect(message.getByText('Неизвестные подстановки: days')).toBeVisible()
  await message.getByTestId('message-ru').fill('Льготный период: осталось {days_left}.')
  await page.getByTestId('profile-save').click()
  await expect(page.getByText(`Сохранена версия ${String(before + 1)}`)).toBeVisible()
  await expect(history).toHaveCount(before + 1)
})
