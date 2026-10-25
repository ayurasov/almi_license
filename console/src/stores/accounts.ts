// Store of the Users screen (E07-09): an administrator creates, blocks and resets console users.
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { NetworkError } from '@/api/problem'

type Schemas = components['schemas']
export type Account = Schemas['Account']
export type ManagedRole = Schemas['RoleEnum']
export type IssuedPassword = Schemas['IssuedPassword']

function required<T>(data: T | undefined): T {
  if (data === undefined) throw new NetworkError('empty response')
  return data
}

export const useAccountsStore = defineStore('accounts', () => {
  const items = ref<Account[]>([])
  const loading = ref(false)
  const failed = ref<'network' | 'server' | null>(null)

  function replace(account: Account): void {
    const index = items.value.findIndex((item) => item.username === account.username)
    if (index >= 0) items.value.splice(index, 1, account)
    else items.value.push(account)
  }

  async function list(): Promise<void> {
    loading.value = true
    failed.value = null
    try {
      const { data } = await api.GET('/api/admin/accounts')
      items.value = data ?? []
    } catch (error) {
      items.value = []
      failed.value = error instanceof NetworkError ? 'network' : 'server'
    } finally {
      loading.value = false
    }
  }

  /** The password of the result is shown once and is not kept in the store. */
  /** customerId binds a customer viewer to its customer (E07-08). */
  async function create(username: string, role: ManagedRole, customerId?: string): Promise<IssuedPassword> {
    const body = customerId ? { username, role, customer_id: customerId } : { username, role }
    const { data } = await api.POST('/api/admin/accounts', { body })
    const issued = required(data)
    replace(issued.account)
    return issued
  }

  async function update(username: string, change: { role?: ManagedRole; active?: boolean }): Promise<Account> {
    const { data } = await api.PATCH('/api/admin/accounts/{username}', {
      params: { path: { username } },
      body: change,
    })
    const account = required(data)
    replace(account)
    return account
  }

  async function resetPassword(username: string): Promise<IssuedPassword> {
    const { data } = await api.POST('/api/admin/accounts/{username}/password', {
      params: { path: { username } },
    })
    const issued = required(data)
    replace(issued.account)
    return issued
  }

  return { items, loading, failed, list, create, update, resetPassword }
})
