import { generateKeyPairSync, randomUUID, sign } from 'node:crypto'

import { expect, test } from '@playwright/test'

import { apiPost, innOf, signIn } from './helpers'

// The device key of the test is made here; the server knows nothing about it (section 10 of
// document 2: the request is signed by the key it carries).
function alkRequest(licenseKey: string): string {
  const { privateKey, publicKey } = generateKeyPairSync('ed25519')
  const part = (value: unknown): string => Buffer.from(JSON.stringify(value)).toString('base64url')
  const payload = {
    type: 'activate',
    license_key: licenseKey,
    product: { code: 'alteroffice-desktop', version: '3.2.0' },
    instance: {
      instance_id: randomUUID(),
      subject_type: 'device',
      name: 'WS-OFFLINE',
      os: { family: 'windows', name: 'Windows 11 Pro', version: '10.0', arch: 'x86_64' },
    },
    fingerprint: { scheme: 'fp-v1', components: { disk: 'pX0', board: 'Zr4', cpu: 'k1Q', mac: 's9V' } },
    device_pubkey: String(publicKey.export({ format: 'jwk' }).x),
    nonce: Buffer.from(randomUUID()).toString('base64url'),
    created: new Date().toISOString(),
  }
  const input = `${part({ alg: 'EdDSA', typ: 'alm-req+jws', kid: 'device' })}.${part(payload)}`
  const signature = sign(null, Buffer.from(input), privateKey).toString('base64url')
  return JSON.stringify({ format: 'alk-req', version: 1, payload: `${input}.${signature}` })
}

test('a customer activates a computer offline on the public page', async ({ page }) => {
  await signIn(page, '/licenses')
  const products = (await (await page.request.get('/api/admin/products')).json()) as {
    id: string
    code: string
    default_metric_id: string
  }[]
  const desktop = products.find((product) => product.code === 'alteroffice-desktop')
  const customer = await apiPost(page, '/api/admin/customers', {
    name: `ООО «Офлайн ${String(Date.now())}»`,
    inn: innOf((Date.now() + 11) % 10_000_000),
  })
  const license = await apiPost(page, '/api/admin/licenses', {
    customer_id: customer.id,
    product_id: desktop?.id,
    metric_id: desktop?.default_metric_id,
    type: 'subscription',
    limit: 5,
    valid_from: new Date(Date.now() - 86_400_000).toISOString(),
    valid_until: new Date(Date.now() + 365 * 86_400_000).toISOString(),
  })
  const issued = await apiPost(page, `/api/admin/licenses/${String(license.id)}/keys`, {})
  const request = alkRequest(String(issued.key))

  // Without a session: a new context has no cookies of the console.
  const browser = page.context().browser()
  if (!browser) throw new Error('no browser')
  const anonymous = await browser.newPage({ baseURL: page.url() })
  await anonymous.goto('/offline')
  await expect(anonymous.getByRole('heading', { name: 'Офлайн-активация' })).toBeVisible()

  await anonymous.getByTestId('offline-file').setInputFiles({
    name: 'broken.alk-req',
    mimeType: 'application/json',
    buffer: Buffer.from('{"format":"alk-req","version":1,"payload":"a.b"}'),
  })
  await expect(anonymous.getByTestId('offline-error')).toBeVisible()

  const download = anonymous.waitForEvent('download')
  await anonymous.getByTestId('offline-file').setInputFiles({
    name: 'WS-OFFLINE.alk-req',
    mimeType: 'application/json',
    buffer: Buffer.from(request),
  })
  expect((await download).suggestedFilename()).toMatch(/\.alk-lic$/)
  await expect(anonymous.getByTestId('offline-ready')).toBeVisible()
  await expect(anonymous.getByTestId('offline-error')).toHaveCount(0)
  await anonymous.close()
})
