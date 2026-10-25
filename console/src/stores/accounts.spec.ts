import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import { NetworkError } from '@/api/problem'

import { type Account, useAccountsStore } from './accounts'

const account: Account = {
  username: 'ivanova',
  role: 'operator',
  active: true,
  locked_until: null,
  last_login: null,
  created_at: '2026-10-24T08:00:00Z',
  customer_id: null,
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useAccountsStore', () => {
  it('lists users and remembers a network failure', async () => {
    const get = vi.spyOn(api, 'GET').mockResolvedValueOnce({ data: [account], response: new Response() })
    const store = useAccountsStore()
    await store.list()
    expect(store.items).toEqual([account])

    get.mockRejectedValueOnce(new NetworkError())
    await store.list()
    expect(store.failed).toBe('network')
  })

  it('creates, blocks and resets, keeping the row and not the password', async () => {
    const generated = ['first', 'second'].join('-')
    const post = vi.spyOn(api, 'POST').mockResolvedValue({ data: { account, password: generated }, response: new Response() })
    const patch = vi.spyOn(api, 'PATCH').mockResolvedValue({ data: { ...account, active: false }, response: new Response() })
    const store = useAccountsStore()

    expect((await store.create('ivanova', 'operator')).password).toBe(generated)
    expect(post).toHaveBeenCalledWith('/api/admin/accounts', { body: { username: 'ivanova', role: 'operator' } })
    await store.update('ivanova', { active: false })
    expect(patch).toHaveBeenCalledWith('/api/admin/accounts/{username}', {
      params: { path: { username: 'ivanova' } },
      body: { active: false },
    })
    expect(store.items).toEqual([{ ...account, active: false }])

    await store.resetPassword('ivanova')
    expect(post).toHaveBeenLastCalledWith('/api/admin/accounts/{username}/password', {
      params: { path: { username: 'ivanova' } },
    })
    expect(JSON.stringify(store.$state)).not.toContain(generated)
  })
})
