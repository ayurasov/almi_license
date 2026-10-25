// Store of the Journal screen (E10-04): audit events by object, user, type and period, and CSV.
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { NetworkError } from '@/api/problem'

export type AuditEvent = components['schemas']['AuditEvent']

export interface AuditFilter {
  objectType: string
  objectId: string
  actor: string
  action: string
  since: Date | null
  until: Date | null
}

export const EMPTY_FILTER: AuditFilter = { objectType: '', objectId: '', actor: '', action: '', since: null, until: null }
export const PAGE_SIZE = 50

function query(filter: AuditFilter): Record<string, string | undefined> {
  return {
    object_type: filter.objectType || undefined,
    object_id: filter.objectId.trim() || undefined,
    actor: filter.actor.trim() || undefined,
    action: filter.action.trim() || undefined,
    since: filter.since?.toISOString(),
    until: filter.until?.toISOString(),
  }
}

export const useAuditStore = defineStore('audit', () => {
  const items = ref<AuditEvent[]>([])
  const count = ref(0)
  const loading = ref(false)
  const failed = ref<'network' | 'server' | null>(null)

  async function load(filter: AuditFilter, page = 1): Promise<void> {
    loading.value = true
    failed.value = null
    try {
      const { data } = await api.GET('/api/admin/audit', {
        params: { query: { ...query(filter), page, page_size: PAGE_SIZE } },
      })
      items.value = data?.results ?? []
      count.value = data?.count ?? 0
    } catch (error) {
      items.value = []
      count.value = 0
      failed.value = error instanceof NetworkError ? 'network' : 'server'
    } finally {
      loading.value = false
    }
  }

  /** The CSV of the current filter as a file to save. */
  async function exportCsv(filter: AuditFilter): Promise<Blob> {
    const { data } = await api.GET('/api/admin/audit/export', { params: { query: query(filter) }, parseAs: 'blob' })
    if (!(data instanceof Blob)) throw new NetworkError('empty response')
    return data
  }

  return { items, count, loading, failed, load, exportCsv }
})
