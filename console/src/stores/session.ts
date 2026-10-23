// Console session (E07-02): who is signed in; sign in and out through /api/admin/session.
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { ApiError } from '@/api/problem'

export type Session = components['schemas']['Session']

export const useSessionStore = defineStore('session', () => {
  const user = ref<Session | null>(null)
  const checked = ref(false)

  /** Loads the session once; also gets the CSRF cookie the server sets on this GET. */
  async function load(): Promise<Session | null> {
    try {
      const { data } = await api.GET('/api/admin/session')
      user.value = data ?? null
    } catch (error) {
      if (!(error instanceof ApiError)) throw error
      user.value = null
    } finally {
      checked.value = true
    }
    return user.value
  }

  async function signIn(username: string, password: string): Promise<void> {
    if (!checked.value) await load()
    const { data } = await api.POST('/api/admin/session', { body: { username, password } })
    user.value = data ?? null
  }

  async function signOut(): Promise<void> {
    await api.DELETE('/api/admin/session')
    user.value = null
  }

  function forget(): void {
    user.value = null
  }

  return { user, checked, load, signIn, signOut, forget }
})
