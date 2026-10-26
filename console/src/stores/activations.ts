// Store of the Activations screen (E07-05), built like useCustomersStore (docs/reference-screen.md).
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { NetworkError } from '@/api/problem'

export type Activation = components['schemas']['Activation']
export type Directive = components['schemas']['Directive']
export type DirectiveType = components['schemas']['DirectiveCreateTypeEnum']
export type DirectiveBody = components['schemas']['DirectiveCreate']
export const DIRECTIVE_TYPES: DirectiveType[] = [
  'refresh_now',
  'update_trust',
  'set_check_interval',
  'show_message',
  'set_server_url',
  'rebind',
  'release',
]

export interface ActivationQuery {
  page: number
  pageSize: number
  ordering: string
  licenseId: string
  search: string
  status: string
}

export const DEFAULT_ACTIVATION_QUERY: ActivationQuery = {
  page: 1,
  pageSize: 20,
  ordering: '-last_seen_at',
  licenseId: '',
  search: '',
  status: '',
}

export const useActivationsStore = defineStore('activations', () => {
  const items = ref<Activation[]>([])
  const total = ref(0)
  const loading = ref(false)
  const failed = ref<'network' | 'server' | null>(null)

  async function list(query: ActivationQuery): Promise<void> {
    loading.value = true
    failed.value = null
    try {
      const { data } = await api.GET('/api/admin/activations', {
        params: {
          query: {
            page: query.page,
            page_size: query.pageSize,
            ordering: query.ordering,
            license_id: query.licenseId || undefined,
            search: query.search || undefined,
            status: query.status || undefined,
          },
        },
      })
      items.value = data?.results ?? []
      total.value = data?.count ?? 0
    } catch (error) {
      items.value = []
      total.value = 0
      failed.value = error instanceof NetworkError ? 'network' : 'server'
    } finally {
      loading.value = false
    }
  }

  async function release(activationId: string, reason: string): Promise<Activation> {
    const { data } = await api.POST('/api/admin/activations/{activation_id}/release', {
      params: { path: { activation_id: activationId } },
      body: { reason },
    })
    if (!data) throw new NetworkError('empty response')
    return data
  }

  async function sendDirective(activationId: string, body: DirectiveBody): Promise<Directive> {
    const { data } = await api.POST('/api/admin/activations/{activation_id}/directives', {
      params: { path: { activation_id: activationId } },
      body,
    })
    if (!data) throw new NetworkError('empty response')
    return data
  }

  async function directives(activationId: string): Promise<Directive[]> {
    const { data } = await api.GET('/api/admin/activations/{activation_id}/directives', {
      params: { path: { activation_id: activationId } },
    })
    return data ?? []
  }

  return { items, total, loading, failed, list, release, sendDirective, directives }
})
