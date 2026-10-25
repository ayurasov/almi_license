import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import { NetworkError } from '@/api/problem'

import { EMPTY_FILTER, PAGE_SIZE, useAuditStore } from './audit'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useAuditStore', () => {
  it('sends only the filters that are set', async () => {
    const event = { seq: 3, at: '2026-11-02T08:15:00Z', actor: 'user:ivanova', action: 'license.suspended',
      object_type: 'license', object_id: 'l1', ip: null, data: {} }
    const get = vi.spyOn(api, 'GET').mockResolvedValue({ data: { count: 1, results: [event] }, response: new Response() })
    const store = useAuditStore()
    const since = new Date('2026-11-01T00:00:00Z')

    await store.load({ ...EMPTY_FILTER, actor: ' ivanova ', action: 'license.', since }, 2)

    expect(get).toHaveBeenCalledWith('/api/admin/audit', {
      params: {
        query: { object_type: undefined, object_id: undefined, actor: 'ivanova', action: 'license.',
          since: '2026-11-01T00:00:00.000Z', until: undefined, page: 2, page_size: PAGE_SIZE },
      },
    })
    expect(store.items).toEqual([event])
    expect(store.count).toBe(1)

    get.mockRejectedValue(new NetworkError())
    await store.load(EMPTY_FILTER)
    expect(store.failed).toBe('network')
    expect(store.items).toEqual([])
  })

  it('downloads the CSV as a blob', async () => {
    const blob = new Blob(['seq'])
    vi.spyOn(api, 'GET').mockResolvedValue({ data: blob, response: new Response() })
    expect(await useAuditStore().exportCsv(EMPTY_FILTER)).toBe(blob)
  })
})
