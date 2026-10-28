import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'

import { useSessionStore } from './session'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useSessionStore', () => {
  it('changes the own password and keeps the session without the temporary mark', async () => {
    const user = { username: 'petrov', role: 'operator' as const, customer_id: null, must_change_password: true }
    vi.spyOn(api, 'POST')
      .mockResolvedValueOnce({ data: user, response: new Response() })
      .mockResolvedValueOnce({ data: { ...user, must_change_password: false }, response: new Response() })
    vi.spyOn(api, 'GET').mockResolvedValue({ data: undefined, response: new Response() })
    const store = useSessionStore()
    await store.signIn('petrov', 'temporary')
    expect(store.user?.must_change_password).toBe(true)
    await store.changePassword('temporary', 'Ветер-над-Волгой-2026')
    expect(api.POST).toHaveBeenLastCalledWith('/api/admin/session/password', {
      body: { current_password: 'temporary', new_password: 'Ветер-над-Волгой-2026' },
    })
    expect(store.user?.must_change_password).toBe(false)
  })
})
