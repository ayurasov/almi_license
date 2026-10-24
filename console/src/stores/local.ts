// Store of a local server (E09-01, E09-03): first-run wizard and the rights package.
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { NetworkError } from '@/api/problem'

type Schemas = components['schemas']
export type LocalStatus = Schemas['LocalStatus']
export type SetupResult = Schemas['SetupResult']

function required<T>(data: T | undefined): T {
  if (data === undefined) throw new NetworkError('empty response')
  return data
}

export const useLocalStore = defineStore('local', () => {
  const status = ref<LocalStatus | null>(null)

  async function load(): Promise<LocalStatus> {
    const { data } = await api.GET('/api/admin/setup')
    status.value = required(data)
    return status.value
  }

  /** Online: registers at once; files only: the result carries the request file to save. */
  async function setup(registrationCode: string, centralUrl: string): Promise<SetupResult> {
    const { data } = await api.POST('/api/admin/setup', {
      body: { registration_code: registrationCode, central_url: centralUrl },
    })
    const result = required(data)
    status.value = result.status
    return result
  }

  async function upload(file: File): Promise<LocalStatus> {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.POST('/api/admin/package', { body: { file: file.name }, bodySerializer: () => form })
    status.value = required(data)
    return status.value
  }

  async function sync(): Promise<LocalStatus> {
    const { data } = await api.POST('/api/admin/package/sync')
    status.value = required(data)
    return status.value
  }

  return { status, load, setup, upload, sync }
})
