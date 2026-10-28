// Screenshots of the console for docs/user-guide.md and docs/deployment.md (make screenshots).
//
//   CONSOLE_URL=https://localhost:8443 CONSOLE_USER=admin CONSOLE_PASSWORD=… \
//     node tools/screenshots/console.cjs docs/images/console [central|local]
//
// Runs against an installed server with test data (deploy/central with DEV_ISSUER=1 and
// manage.py seed_minimal). Every step is independent: a failed one is reported and skipped.
// Keys, registration codes and passwords shown once are replaced by a sample before the shot.
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require('playwright')

const base = process.env.CONSOLE_URL ?? 'https://localhost:8443'
const user = process.env.CONSOLE_USER ?? 'admin'
const password = process.env.CONSOLE_PASSWORD ?? ''
const out = process.argv[2] ?? 'docs/images/console'
const mode = process.argv[3] ?? 'central'
const failed = []

async function shot(page, name, options = {}) {
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(400) // PrimeVue transitions of dialogs and toasts
  await page.screenshot({ path: path.join(out, `${name}.png`), ...options })
  console.log(`ok   ${name}`)
}

async function step(name, action) {
  try {
    await action()
  } catch (error) {
    failed.push(name)
    console.log(`FAIL ${name}: ${String(error).split('\n')[0]}`)
  }
}

// Values shown once are not put into the documentation.
async function mask(page, testId, sample) {
  await page.getByTestId(testId).evaluate((node, text) => {
    node.textContent = text
  }, sample)
}

async function closeDialogs(page) {
  for (let i = 0; i < 3 && (await page.locator('.p-dialog').count()) > 0; i++) {
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)
  }
}

async function openLicense(page, text) {
  await page.goto(`${base}/licenses`)
  const row = page.getByTestId('licenses-table').locator('tbody tr', { hasText: text }).first()
  await row.getByTestId('license-open').click()
  await page.getByRole('tab', { name: 'Параметры' }).waitFor()
}

async function central(page) {
  await step('02-customers', async () => {
    await page.goto(`${base}/customers`)
    await page.getByTestId('customers-table').locator('tbody tr').first().waitFor()
    await shot(page, '02-customers')
  })
  await step('03-customer-new', async () => {
    await page.getByTestId('customer-create').click()
    await page.locator('.p-dialog').waitFor()
    await shot(page, '03-customer-new')
    await closeDialogs(page)
  })
  await step('04-licenses', async () => {
    await page.goto(`${base}/licenses`)
    await page.getByTestId('licenses-table').locator('tbody tr').first().waitFor()
    await shot(page, '04-licenses')
  })
  await step('05-license-params', async () => {
    await openLicense(page, 'Тестовый заказчик 1')
    await shot(page, '05-license-params')
  })
  await step('06-license-keys', async () => {
    await page.getByRole('tab', { name: 'Ключи' }).click()
    await shot(page, '06-license-keys')
    await page.getByTestId('issue-key').click()
    await page.getByTestId('issued-key').waitFor()
    await mask(page, 'issued-key', '4426-XXXX-XXXX-XXXX')
    await shot(page, '07-license-key-issued')
    await page.getByTestId('issued-key-close').click()
  })
  for (const [tab, name] of [
    ['Активации', '08-license-activations'],
    ['История', '09-license-history'],
    ['Использование', '10-license-usage'],
  ]) {
    await step(name, async () => {
      await page.getByRole('tab', { name: tab }).click()
      await shot(page, name)
    })
  }
  for (const [action, name] of [
    ['renew', '11-action-renew'],
    ['settings', '12-action-settings'],
    ['liftBlock', '13-action-lift-block'],
    ['suspend', '14-action-suspend'],
    ['transfer', '15-action-transfer'],
    ['revoke', '16-action-revoke'],
  ]) {
    await step(name, async () => {
      await page.getByTestId(`action-${action}`).click()
      await page.locator('.p-dialog').waitFor()
      await shot(page, name)
      await closeDialogs(page)
    })
  }
  await step('17-license-directive', async () => {
    await page.getByTestId('action-directive').click()
    await page.getByTestId('directive-type').click()
    await page.getByRole('option', { name: 'Перевести на другой сервер' }).click()
    await page.getByTestId('directive-url').fill('https://license.corp.local')
    await shot(page, '17-license-directive')
    await closeDialogs(page)
  })
  await step('18-activations', async () => {
    await page.goto(`${base}/activations`)
    await page.getByTestId('activations-table').locator('tbody tr').first().waitFor()
    await shot(page, '18-activations')
  })
  await step('19-activation-release', async () => {
    await page.getByTestId('activation-release').first().click()
    await page.locator('.p-dialog').waitFor()
    await shot(page, '19-activation-release')
    await closeDialogs(page)
  })
  await step('20-activation-directive', async () => {
    await page.getByTestId('activation-directive').first().click()
    await page.getByTestId('directive-type').click()
    await page.getByRole('option', { name: 'Показать сообщение' }).click()
    await page.getByTestId('directive-text').fill('Плановые работы на сервере лицензирования 10.11 с 22:00 до 23:00.')
    await shot(page, '20-activation-directive')
    await closeDialogs(page)
  })
  await step('21-import', async () => {
    await page.goto(`${base}/import`)
    await shot(page, '21-import')
    const sample = path.resolve(__dirname, '../../server/tests/fixtures/lk-export-sample.xlsx')
    await page.getByTestId('import-file').setInputFiles(sample)
    await page.getByTestId('import-upload').click()
    await page.getByTestId('import-summary').waitFor()
    await shot(page, '22-import-preview')
    await page.getByTestId('import-next').click()
    await shot(page, '23-import-mapping')
  })
  await step('24-catalog', async () => {
    await page.goto(`${base}/catalog`)
    await page.getByTestId('products-table').locator('tbody tr').first().click()
    await page.getByTestId('product-details').waitFor()
    await shot(page, '24-catalog')
  })
  await step('25-profiles', async () => {
    await page.goto(`${base}/profiles`)
    await page.getByTestId('profiles-table').locator('tbody tr').first().click()
    await page.getByTestId('profile-editor').waitFor()
    await shot(page, '25-profiles', { fullPage: true })
  })
  await step('26-servers', async () => {
    await page.goto(`${base}/servers`)
    await shot(page, '26-servers')
    await page.getByTestId('server-create').click()
    await page.locator('.p-dialog').waitFor()
    await shot(page, '27-server-new')
    await closeDialogs(page)
  })
  await step('28-stats', async () => {
    await page.goto(`${base}/stats`)
    await page.getByTestId('stats-tiles').waitFor()
    await shot(page, '28-stats', { fullPage: true })
  })
  await step('29-audit', async () => {
    await page.goto(`${base}/audit`)
    await page.getByTestId('audit-table').locator('tbody tr').first().waitFor()
    await shot(page, '29-audit')
  })
  await step('30-users', async () => {
    await page.goto(`${base}/users`)
    await page.getByTestId('users-table').locator('tbody tr').first().waitFor()
    await shot(page, '30-users')
    await page.getByTestId('user-create').click()
    await page.locator('.p-dialog').waitFor()
    await shot(page, '31-user-new')
    await closeDialogs(page)
  })
}

async function local(page) {
  await step('40-setup', async () => {
    await page.goto(`${base}/setup`)
    await page.getByTestId('setup-code').waitFor()
    await shot(page, '40-setup')
  })
  await step('41-package', async () => {
    await page.goto(`${base}/package`)
    await shot(page, '41-package', { fullPage: true })
  })
}

async function main() {
  fs.mkdirSync(out, { recursive: true })
  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    locale: 'ru-RU',
  })
  context.setDefaultTimeout(10000)
  const page = await context.newPage()
  await step('01-login', async () => {
    await page.goto(`${base}/login`)
    await page.getByLabel('Логин').waitFor()
    await shot(page, mode === 'local' ? '39-login-local' : '01-login')
    await page.getByLabel('Логин').fill(user)
    await page.locator('#password').fill(password)
    await page.getByRole('button', { name: 'Войти' }).click()
    await page.getByTestId('current-user').waitFor()
  })
  if (mode === 'local') await local(page)
  else await central(page)
  if (mode !== 'local') {
    const visitor = await browser.newPage({ viewport: { width: 1440, height: 900 }, ignoreHTTPSErrors: true })
    await step('32-offline-portal', async () => {
      await visitor.goto(`${base}/offline`)
      await visitor.getByTestId('offline-file').waitFor({ state: 'attached' })
      await shot(visitor, '32-offline-portal')
      const request = process.env.OFFLINE_REQUEST
      if (request) {
        await visitor.getByTestId('offline-file').setInputFiles(request)
        await visitor.getByTestId('offline-ready').waitFor({ timeout: 15000 })
        await shot(visitor, '33-offline-portal-ready')
      }
    })
  }
  await browser.close()
  if (failed.length > 0) {
    console.log(`failed steps: ${failed.join(', ')}`)
    process.exitCode = 1
  }
}

void main()
