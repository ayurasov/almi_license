// Store of the Statistics screen (E10-01, E10-02): summary by licence and the XLSX export.
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { NetworkError } from '@/api/problem'

export type Stats = components['schemas']['Stats']
export type LicenseStats = components['schemas']['LicenseStats']

export interface StatsFilter {
  customerId: string
  productId: string
}

function query(filter: StatsFilter): { customer_id?: string; product_id?: string } {
  return { customer_id: filter.customerId || undefined, product_id: filter.productId || undefined }
}

export const useStatsStore = defineStore('stats', () => {
  const stats = ref<Stats | null>(null)
  const loading = ref(false)
  const failed = ref<'network' | 'server' | null>(null)

  async function load(filter: StatsFilter): Promise<void> {
    loading.value = true
    failed.value = null
    try {
      const { data } = await api.GET('/api/admin/stats', { params: { query: query(filter) } })
      stats.value = data ?? null
    } catch (error) {
      stats.value = null
      failed.value = error instanceof NetworkError ? 'network' : 'server'
    } finally {
      loading.value = false
    }
  }

  /** The XLSX of the current filter as a file to save. */
  async function exportXlsx(filter: StatsFilter): Promise<Blob> {
    const { data } = await api.GET('/api/admin/stats/export', { params: { query: query(filter) }, parseAs: 'blob' })
    if (!(data instanceof Blob)) throw new NetworkError('empty response')
    return data
  }

  return { stats, loading, failed, load, exportXlsx }
})
