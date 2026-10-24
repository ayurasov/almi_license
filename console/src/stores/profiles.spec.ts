import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import { NetworkError } from '@/api/problem'

import { useProfilesStore } from './profiles'

const v3 = { code: 'office.commercial', version: 3, params: { grace_days: 14 }, created_at: '2026-10-01T00:00:00Z' }
const v4 = { ...v3, version: 4, params: { grace_days: 21 } }

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useProfilesStore', () => {
  it('lists the latest versions and remembers a network failure', async () => {
    const get = vi.spyOn(api, 'GET').mockResolvedValueOnce({ data: [v3], response: new Response() })
    const store = useProfilesStore()
    await store.list()
    expect(get).toHaveBeenCalledWith('/api/admin/profiles')
    expect(store.items).toEqual([v3])

    get.mockRejectedValueOnce(new NetworkError())
    await store.list()
    expect(store.failed).toBe('network')
    expect(store.items).toEqual([])
  })

  it('saves a new version, replaces the row and reloads the history', async () => {
    const get = vi.spyOn(api, 'GET')
    get.mockResolvedValueOnce({ data: [v3], response: new Response() })
    get.mockResolvedValueOnce({ data: [v4, v3], response: new Response() })
    const post = vi.spyOn(api, 'POST').mockResolvedValue({ data: v4, response: new Response() })
    const store = useProfilesStore()
    await store.list()

    await store.save('office.commercial', v4.params)

    expect(post).toHaveBeenCalledWith('/api/admin/profiles/{code}', {
      params: { path: { code: 'office.commercial' } },
      body: { params: v4.params },
    })
    expect(store.items).toEqual([v4])
    expect(store.versions.map((v) => v.version)).toEqual([4, 3])
  })
})
