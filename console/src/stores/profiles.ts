// Store of the Profiles screen (E07-06): every save is a new version on the server (E01-03).
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { NetworkError } from '@/api/problem'

export type Profile = components['schemas']['Profile']
export type ProfileParams = Profile['params']

export const useProfilesStore = defineStore('profiles', () => {
  const items = ref<Profile[]>([])
  const versions = ref<Profile[]>([])
  const loading = ref(false)
  const failed = ref<'network' | 'server' | null>(null)

  async function list(): Promise<void> {
    loading.value = true
    failed.value = null
    try {
      const { data } = await api.GET('/api/admin/profiles')
      items.value = data ?? []
    } catch (error) {
      items.value = []
      failed.value = error instanceof NetworkError ? 'network' : 'server'
    } finally {
      loading.value = false
    }
  }

  async function history(code: string): Promise<Profile[]> {
    const { data } = await api.GET('/api/admin/profiles/{code}', { params: { path: { code } } })
    versions.value = data ?? []
    return versions.value
  }

  async function save(code: string, params: ProfileParams): Promise<Profile> {
    const { data } = await api.POST('/api/admin/profiles/{code}', {
      params: { path: { code } },
      body: { params },
    })
    if (!data) throw new NetworkError('empty response')
    const index = items.value.findIndex((item) => item.code === code)
    if (index >= 0) items.value.splice(index, 1, data)
    else items.value.push(data)
    await history(code)
    return data
  }

  return { items, versions, loading, failed, list, history, save }
})
