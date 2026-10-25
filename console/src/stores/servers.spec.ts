import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import { NetworkError } from '@/api/problem'

import { type LocalServer, useServersStore } from './servers'

const server: LocalServer = {
  id: '6f1c2a4e-8b3d-4c5f-9e7a-1b2c3d4e5f60',
  server_id: 'srv_01JABF8Q4W2N8C1R7ZB0Y5K6M3',
  customer_id: '6f1c2a4e-8b3d-4c5f-9e7a-1b2c3d4e5f61',
  name: 'ЦОД',
  status: 'pending',
  allocations: { lic: 3 },
  registered: false,
  code_expires_at: '2026-11-09T00:00:00Z',
  last_package_seq: 0,
  last_seen_at: null,
  created_at: '2026-11-02T00:00:00Z',
  package_valid_until: null,
  package_expires_soon: false,
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useServersStore', () => {
  it('lists servers and remembers a network failure', async () => {
    const get = vi.spyOn(api, 'GET').mockResolvedValueOnce({ data: [server], response: new Response() })
    const store = useServersStore()
    await store.list()
    expect(store.items).toEqual([server])
    get.mockRejectedValueOnce(new NetworkError())
    await store.list()
    expect(store.failed).toBe('network')
  })

  it('creates a server with seats and keeps the row, not the code', async () => {
    const code = ['ABCDE', 'FGHJK'].join('-')
    const post = vi.spyOn(api, 'POST').mockResolvedValue({ data: { server, code }, response: new Response() })
    const store = useServersStore()

    expect((await store.create(server.customer_id, 'ЦОД', { lic: 3 })).code).toBe(code)
    expect(post).toHaveBeenCalledWith('/api/admin/local-servers', {
      body: { customer_id: server.customer_id, name: 'ЦОД', allocations: { lic: 3 } },
    })
    expect(store.items).toEqual([server])
    expect(JSON.stringify(store.$state)).not.toContain(code)
  })
})
