import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'

import { useInstanceStore } from './instance'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useInstanceStore', () => {
  it('hides central sections on a local server and loads the mode once', async () => {
    const get = vi.spyOn(api, 'GET').mockResolvedValue({ data: { mode: 'local' }, response: new Response() })
    const store = useInstanceStore()
    await store.load()
    await store.load()

    expect(get).toHaveBeenCalledTimes(1)
    expect(store.allows('catalog')).toBe(false)
    expect(store.allows('import')).toBe(false)
    expect(store.allows('licenses')).toBe(true)
  })

  it('allows everything on the central server', async () => {
    vi.spyOn(api, 'GET').mockResolvedValue({ data: { mode: 'central' }, response: new Response() })
    const store = useInstanceStore()
    await store.load()
    expect(store.allows('catalog')).toBe(true)
  })
})
