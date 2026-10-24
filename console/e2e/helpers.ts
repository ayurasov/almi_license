import { expect, type Page } from '@playwright/test'

export async function signIn(page: Page, path: string): Promise<void> {
  await page.goto(path)
  await expect(page).toHaveURL(/\/login/)
  // On a cold Vite start the form can mount again after the first fill: wait for the modules.
  await page.waitForLoadState('networkidle')
  await page.getByLabel('Логин').fill(process.env.E2E_USERNAME ?? '')
  await page.locator('#password').fill(process.env.E2E_PASSWORD ?? '')
  await expect(page.locator('#password')).toHaveValue(process.env.E2E_PASSWORD ?? '')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByTestId('current-user')).toHaveText(process.env.E2E_USERNAME ?? '')
}

/** Admin API call with the session and CSRF cookies of the page (test data setup). */
export async function apiPost(page: Page, path: string, body: unknown): Promise<Record<string, unknown>> {
  const cookies = await page.context().cookies()
  const token = cookies.find((cookie) => cookie.name === 'csrftoken')?.value ?? ''
  const response = await page.request.post(path, { data: body, headers: { 'X-CSRFToken': token } })
  expect(response.ok(), await response.text()).toBe(true)
  return (await response.json()) as Record<string, unknown>
}

// INN with a valid check digit, unique per run (the server keeps INN unique).
export function innOf(seed: number): string {
  const weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
  const body = `77${String(seed).padStart(7, '0').slice(-7)}`
  const sum = weights.reduce((total, weight, i) => total + Number(body.charAt(i)) * weight, 0)
  return body + String((sum % 11) % 10)
}
