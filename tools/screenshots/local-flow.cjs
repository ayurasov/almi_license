// Screenshots of a local server registered by files (docs/user-guide.md, section 9):
// the central console issues a code, the wizard of the local server writes .alk-req, the central
// server answers with the package .alk, the local server applies it and reports its usage.
//
//   CENTRAL_URL=https://localhost:8443 LOCAL_URL=https://localhost:9443 \
//   CENTRAL_PASSWORD=… LOCAL_PASSWORD=… node tools/screenshots/local-flow.cjs docs/images/console
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { chromium } = require('playwright')

const central = process.env.CENTRAL_URL ?? 'https://localhost:8443'
const local = process.env.LOCAL_URL ?? 'https://localhost:9443'
const out = process.argv[2] ?? 'docs/images/console'
const files = fs.mkdtempSync(path.join(os.tmpdir(), 'almi-local-flow-'))

async function shot(page, name, options = {}) {
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(400)
  await page.screenshot({ path: path.join(out, `${name}.png`), ...options })
  console.log(`ok   ${name}`)
}

async function signIn(page, base, password, name) {
  await page.goto(`${base}/login`)
  await page.getByLabel('Логин').waitFor()
  if (name) await shot(page, name)
  await page.getByLabel('Логин').fill('admin')
  await page.locator('#password').fill(password)
  await page.getByRole('button', { name: 'Войти' }).click()
  await page.getByTestId('current-user').waitFor()
}

async function saveDownload(page, action, name) {
  const [file] = await Promise.all([page.waitForEvent('download'), action()])
  const target = path.join(files, name)
  await file.saveAs(target)
  return target
}

async function main() {
  fs.mkdirSync(out, { recursive: true })
  const browser = await chromium.launch()
  const options = { viewport: { width: 1440, height: 900 }, ignoreHTTPSErrors: true, acceptDownloads: true }
  const centralPage = await (await browser.newContext(options)).newPage()
  const localPage = await (await browser.newContext(options)).newPage()
  centralPage.setDefaultTimeout(15000)
  localPage.setDefaultTimeout(15000)

  // 1. The operator of ALMI creates the local server and gets a code.
  await signIn(centralPage, central, process.env.CENTRAL_PASSWORD ?? '')
  await centralPage.goto(`${central}/servers`)
  await centralPage.getByTestId('server-create').click()
  await centralPage.getByTestId('server-customer').click()
  await centralPage.getByRole('option', { name: /Тестовый заказчик 2/ }).click()
  await centralPage.getByTestId('server-name').fill('Филиал «Бета», ЦОД')
  // The licence of 5 seats (the one of 2 seats is past its term): one of them goes to the server.
  await centralPage.getByTestId('server-seats').nth(1).locator('input').fill('1')
  await shot(centralPage, '34-server-new-filled')
  await centralPage.getByTestId('server-save').click()
  const codeNode = centralPage.getByTestId('registration-code')
  await codeNode.waitFor().catch(async (error) => {
    await centralPage.screenshot({ path: path.join(files, 'failed-save.png') })
    throw error
  })
  const code = (await codeNode.textContent()).trim()
  await codeNode.evaluate((node) => {
    node.textContent = 'XXXXX-XXXXX-XXXXX'
  })
  await shot(centralPage, '35-registration-code')
  await centralPage.getByTestId('registration-code-close').click()

  // 2. The administrator of the customer runs the first-run wizard: exchange by files.
  await signIn(localPage, local, process.env.LOCAL_PASSWORD ?? '', '39-login-local')
  await localPage.goto(`${local}/setup`)
  await localPage.getByTestId('setup-code').waitFor()
  await shot(localPage, '40-setup')
  await localPage.getByTestId('setup-code').fill(code)
  await localPage.getByTestId('setup-exchange').getByText('Только файлы').click()
  await localPage.getByTestId('setup-code').evaluate((node) => {
    node.value = 'XXXXX-XXXXX-XXXXX'
  })
  await shot(localPage, '41-setup-files')
  await localPage.getByTestId('setup-code').fill(code)
  const request = await saveDownload(localPage, () => localPage.getByTestId('setup-submit').click(), 'server.alk-req')
  await localPage.getByTestId('setup-file-ready').waitFor()
  await shot(localPage, '42-setup-file-ready')

  // 3. The central server answers the request with the first package.
  await centralPage.goto(`${central}/servers`)
  await centralPage.getByTestId('servers-table').locator('tbody tr').first().waitFor()
  const pkg = await saveDownload(
    centralPage,
    () => centralPage.getByTestId('register-file').setInputFiles(request),
    'server.alk',
  )
  await centralPage.waitForTimeout(1000)
  await centralPage.reload()
  await shot(centralPage, '36-servers-registered')

  // 4. The local server applies the package and makes its usage report.
  await localPage.goto(`${local}/package`)
  await localPage.getByTestId('package-file').setInputFiles(pkg)
  await localPage.getByTestId('package-seq').waitFor()
  await localPage.waitForTimeout(800)
  await shot(localPage, '43-package', { fullPage: true })
  const report = await saveDownload(localPage, () => localPage.getByTestId('usage-report').click(), 'usage.alk-usage')
  await centralPage.goto(`${central}/servers`)
  await centralPage.getByTestId('usage-file').setInputFiles(report)
  await centralPage.waitForTimeout(1500)
  await shot(centralPage, '37-servers-usage')

  await browser.close()
  fs.rmSync(files, { recursive: true, force: true })
}

main().catch((error) => {
  console.error(error)
  // The browser of a failed run would keep the process alive.
  process.exit(1)
})
