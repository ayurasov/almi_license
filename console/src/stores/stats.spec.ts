import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import { NetworkError } from '@/api/problem'

import { useStatsStore } from './stats'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useStatsStore', () => {
  it('passes the filter and keeps the summary', async () => {
    const stats = { licenses: 1, limit: 10, active: 2, in_reserve: 1, free: 8, released_auto: 0, conflicts: 0,
      last_seen_at: null, by_version: {}, by_os: {}, rows: [] }
    const get = vi.spyOn(api, 'GET').mockResolvedValue({ data: stats, response: new Response() })
    const store = useStatsStore()

    await store.load({ customerId: 'c1', productId: '' })

    expect(get).toHaveBeenCalledWith('/api/admin/stats', { params: { query: { customer_id: 'c1', product_id: undefined } } })
    expect(store.stats).toEqual(stats)

    get.mockRejectedValue(new NetworkError())
    await store.load({ customerId: '', productId: '' })
    expect(store.failed).toBe('network')
  })

  it('downloads the XLSX as a blob', async () => {
    const blob = new Blob(['xlsx'])
    const get = vi.spyOn(api, 'GET').mockResolvedValue({ data: blob, response: new Response() })
    const store = useStatsStore()
    expect(await store.exportXlsx({ customerId: '', productId: 'p1' })).toBe(blob)
    expect(get).toHaveBeenCalledWith('/api/admin/stats/export', {
      params: { query: { customer_id: undefined, product_id: 'p1' } },
      parseAs: 'blob',
    })
  })
})
