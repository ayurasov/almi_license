import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'

import { DEFAULT_ACTIVATION_QUERY, useActivationsStore } from './activations'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useActivationsStore', () => {
  it('searches by activation id, name or version', async () => {
    const get = vi
      .spyOn(api, 'GET')
      .mockResolvedValue({ data: { count: 0, results: [] }, response: new Response() })
    const store = useActivationsStore()

    await store.list({ ...DEFAULT_ACTIVATION_QUERY, search: 'WS-0451', licenseId: 'l1' })

    expect(get).toHaveBeenCalledWith('/api/admin/activations', {
      params: {
        query: {
          page: 1,
          page_size: 20,
          ordering: '-last_seen_at',
          license_id: 'l1',
          search: 'WS-0451',
          status: undefined,
        },
      },
    })
  })

  it('releases with a reason', async () => {
    const post = vi
      .spyOn(api, 'POST')
      .mockResolvedValue({ data: { activation_id: 'act_1', status: 'released' }, response: new Response() })
    const store = useActivationsStore()

    await store.release('act_1', 'Списан компьютер')

    expect(post).toHaveBeenCalledWith('/api/admin/activations/{activation_id}/release', {
      params: { path: { activation_id: 'act_1' } },
      body: { reason: 'Списан компьютер' },
    })
  })

  it('queues a directive for an activation', async () => {
    const post = vi
      .spyOn(api, 'POST')
      .mockResolvedValue({ data: { id: 'dir_1', state: 'queued' }, response: new Response() })
    const store = useActivationsStore()

    const body = { type: 'set_server_url' as const, params: { url: 'https://license.corp.local', fallback_days: 14 } }
    await store.sendDirective('act_1', body)

    expect(post).toHaveBeenCalledWith('/api/admin/activations/{activation_id}/directives', {
      params: { path: { activation_id: 'act_1' } },
      body,
    })
  })

  it('lists the directives of an activation', async () => {
    vi.spyOn(api, 'GET').mockResolvedValue({ data: [{ id: 'dir_1', state: 'acked' }], response: new Response() })
    const store = useActivationsStore()

    expect(await store.directives('act_1')).toEqual([{ id: 'dir_1', state: 'acked' }])
  })
})
