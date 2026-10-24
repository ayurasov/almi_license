// Store of the Local servers screen (E09-02): servers of customers, seats, registration codes.
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { NetworkError } from '@/api/problem'

type Schemas = components['schemas']
export type LocalServer = Schemas['LocalServer']
export type RegistrationCode = Schemas['RegistrationCode']
export type AlkFile = Schemas['AlkFile']

function required<T>(data: T | undefined): T {
  if (data === undefined) throw new NetworkError('empty response')
  return data
}

/** Saves a JSON document as a file in the browser. */
export function download(name: string, document: unknown): void {
  const blob = new Blob([JSON.stringify(document)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = Object.assign(window.document.createElement('a'), { href: url, download: name })
  link.click()
  URL.revokeObjectURL(url)
}

export const useServersStore = defineStore('servers', () => {
  const items = ref<LocalServer[]>([])
  const loading = ref(false)
  const failed = ref<'network' | 'server' | null>(null)

  function replace(server: LocalServer): void {
    const index = items.value.findIndex((item) => item.id === server.id)
    if (index >= 0) items.value.splice(index, 1, server)
    else items.value.unshift(server)
  }

  async function list(): Promise<void> {
    loading.value = true
    failed.value = null
    try {
      const { data } = await api.GET('/api/admin/local-servers')
      items.value = data ?? []
    } catch (error) {
      items.value = []
      failed.value = error instanceof NetworkError ? 'network' : 'server'
    } finally {
      loading.value = false
    }
  }

  async function create(customerId: string, name: string, allocations: Record<string, number>): Promise<RegistrationCode> {
    const { data } = await api.POST('/api/admin/local-servers', {
      body: { customer_id: customerId, name, allocations },
    })
    const issued = required(data)
    replace(issued.server)
    return issued
  }

  async function newCode(id: string): Promise<RegistrationCode> {
    const { data } = await api.POST('/api/admin/local-servers/{server_uuid}/code', {
      params: { path: { server_uuid: id } },
    })
    const issued = required(data)
    replace(issued.server)
    return issued
  }

  async function setAllocations(id: string, allocations: Record<string, number>): Promise<LocalServer> {
    const { data } = await api.PUT('/api/admin/local-servers/{server_uuid}/allocations', {
      params: { path: { server_uuid: id } },
      body: { allocations },
    })
    const server = required(data)
    replace(server)
    return server
  }

  /** Registration by file: the .alk-req of the server in, its first package .alk out. */
  async function registerFile(file: File): Promise<AlkFile> {
    const form = new FormData()
    form.append('file', file)
    const { data } = await api.POST('/api/admin/local-servers/register-file', {
      body: { file: file.name },
      bodySerializer: () => form,
    })
    await list()
    return required(data)
  }

  return { items, loading, failed, list, create, newCode, setAllocations, registerFile }
})
