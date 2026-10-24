import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import { NetworkError } from '@/api/problem'

import { DEFAULT_LICENSE_QUERY, useLicensesStore } from './licenses'

const license = {
  id: '6f1c2a4e-8b3d-4c5f-9e7a-1b2c3d4e5f60',
  customer_id: 'c1',
  customer_name: 'ООО «Пример»',
  product_id: 'p1',
  edition_id: null,
  type: 'subscription' as const,
  status: 'active' as const,
  limit: 10,
  reserve_pct: null,
  valid_from: '2026-11-01T00:00:00Z',
  valid_until: '2027-10-31T20:59:59Z',
  support_until: null,
  enforcement: '',
  monitor_until: null,
  policy_profile_code: '',
  rights_version: 1,
  key_masks: ['2645-****-****-81ZT'],
}
const ok = (data: unknown) => ({ data, response: new Response() }) as never
const path = { params: { path: { license_id: license.id } } }

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useLicensesStore', () => {
  it('lists with filters as query parameters', async () => {
    const get = vi.spyOn(api, 'GET').mockResolvedValue(ok({ count: 1, results: [license] }))
    const store = useLicensesStore()

    await store.list({ ...DEFAULT_LICENSE_QUERY, status: 'active', expiresBefore: '2028-01-01T00:00:00.000Z' })

    expect(get).toHaveBeenCalledWith('/api/admin/licenses', {
      params: {
        query: {
          page: 1,
          page_size: 20,
          ordering: 'valid_until',
          product_id: undefined,
          customer_id: undefined,
          status: 'active',
          expires_before: '2028-01-01T00:00:00.000Z',
        },
      },
    })
    expect(store.items).toEqual([license])
    expect(store.total).toBe(1)
  })

  it('remembers a network failure', async () => {
    vi.spyOn(api, 'GET').mockRejectedValue(new NetworkError())
    const store = useLicensesStore()
    await store.list(DEFAULT_LICENSE_QUERY)
    expect(store.failed).toBe('network')
  })

  it('sends each action to its endpoint with the reason', async () => {
    const post = vi.spyOn(api, 'POST').mockResolvedValue(ok(license))
    const store = useLicensesStore()

    await store.setStatus(license.id, 'suspend', 'Неоплата')
    await store.setStatus(license.id, 'revoke', 'Расторжение')
    await store.liftBlock(license.id, '2026-12-01T00:00:00.000Z', 'Оплата в пути')
    await store.transfer(license.id, { customer_id: 'c2', reason: 'Реорганизация', document: '' })

    const calls = post.mock.calls as unknown as [string, { body?: unknown }][]
    expect(calls.map(([url, options]) => [url, options.body])).toEqual([
      ['/api/admin/licenses/{license_id}/suspend', { reason: 'Неоплата' }],
      ['/api/admin/licenses/{license_id}/revoke', { reason: 'Расторжение' }],
      ['/api/admin/licenses/{license_id}/lift-block', { until: '2026-12-01T00:00:00.000Z', reason: 'Оплата в пути' }],
      ['/api/admin/licenses/{license_id}/transfer', { customer_id: 'c2', reason: 'Реорганизация', document: '' }],
    ])
  })

  it('issues a key and loads usage and history of the license', async () => {
    vi.spyOn(api, 'POST').mockResolvedValue(ok({ license_id: license.id, key: 'K', key_mask: 'M' }))
    const get = vi.spyOn(api, 'GET').mockResolvedValue(ok([]))
    const store = useLicensesStore()

    expect((await store.issueKey(license.id)).key).toBe('K')
    await store.history(license.id)
    expect(get).toHaveBeenCalledWith('/api/admin/licenses/{license_id}/history', path)
  })

  it('loads products once', async () => {
    const get = vi.spyOn(api, 'GET').mockResolvedValue(ok([{ id: 'p1', code: 'alteroffice-desktop' }]))
    const store = useLicensesStore()
    await store.loadProducts()
    await store.loadProducts()
    expect(get).toHaveBeenCalledTimes(1)
  })
})
