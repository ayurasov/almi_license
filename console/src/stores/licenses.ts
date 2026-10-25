// Store of the Licenses screen (E07-04), built like useCustomersStore (docs/reference-screen.md).
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { NetworkError } from '@/api/problem'

type Schemas = components['schemas']
export type License = Schemas['License']
export type Usage = Schemas['Usage']
export type HistoryEvent = Schemas['HistoryEvent']
export type IssuedKey = Schemas['IssuedKey']
export type Product = Schemas['Product']
export type StatusAction = 'suspend' | 'resume' | 'revoke'
// Actions of the license card, each confirmed in LicenseActionDialog.
export type LicenseAction = 'renew' | StatusAction | 'liftBlock' | 'settings' | 'transfer'

export interface LicenseQuery {
  page: number
  pageSize: number
  ordering: string
  productId: string
  customerId: string
  status: string
  expiresBefore: string
}

export const DEFAULT_LICENSE_QUERY: LicenseQuery = {
  page: 1,
  pageSize: 20,
  ordering: 'valid_until',
  productId: '',
  customerId: '',
  status: '',
  expiresBefore: '',
}

function required<T>(data: T | undefined): T {
  if (data === undefined) throw new NetworkError('empty response')
  return data
}

export const useLicensesStore = defineStore('licenses', () => {
  const items = ref<License[]>([])
  const total = ref(0)
  const loading = ref(false)
  const failed = ref<'network' | 'server' | null>(null)
  const products = ref<Product[]>([])

  async function list(query: LicenseQuery): Promise<void> {
    loading.value = true
    failed.value = null
    try {
      const { data } = await api.GET('/api/admin/licenses', {
        params: {
          query: {
            page: query.page,
            page_size: query.pageSize,
            ordering: query.ordering,
            product_id: query.productId || undefined,
            customer_id: query.customerId || undefined,
            status: query.status || undefined,
            expires_before: query.expiresBefore || undefined,
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

  async function loadProducts(): Promise<void> {
    if (products.value.length > 0) return
    const { data } = await api.GET('/api/admin/products')
    products.value = data ?? []
  }

  function path(id: string) {
    return { params: { path: { license_id: id } } }
  }

  async function get(id: string): Promise<License> {
    return required((await api.GET('/api/admin/licenses/{license_id}', path(id))).data)
  }

  async function renew(id: string, body: Schemas['Renew']): Promise<License> {
    return required((await api.POST('/api/admin/licenses/{license_id}/renew', { ...path(id), body })).data)
  }

  async function setStatus(id: string, action: StatusAction, reason: string): Promise<License> {
    const body = { reason }
    const result =
      action === 'suspend'
        ? await api.POST('/api/admin/licenses/{license_id}/suspend', { ...path(id), body })
        : action === 'resume'
          ? await api.POST('/api/admin/licenses/{license_id}/resume', { ...path(id), body })
          : await api.POST('/api/admin/licenses/{license_id}/revoke', { ...path(id), body })
    return required(result.data)
  }

  async function liftBlock(id: string, until: string, reason: string): Promise<License> {
    const body = { until, reason }
    return required((await api.POST('/api/admin/licenses/{license_id}/lift-block', { ...path(id), body })).data)
  }

  async function updateSettings(id: string, body: Schemas['PatchedSettings']): Promise<License> {
    return required((await api.PATCH('/api/admin/licenses/{license_id}/settings', { ...path(id), body })).data)
  }

  async function transfer(id: string, body: Schemas['Transfer']): Promise<License> {
    return required((await api.POST('/api/admin/licenses/{license_id}/transfer', { ...path(id), body })).data)
  }

  async function issueKey(id: string): Promise<IssuedKey> {
    return required((await api.POST('/api/admin/licenses/{license_id}/keys', path(id))).data)
  }

  async function usage(id: string): Promise<Usage> {
    return required((await api.GET('/api/admin/licenses/{license_id}/usage', path(id))).data)
  }

  async function history(id: string): Promise<HistoryEvent[]> {
    return required((await api.GET('/api/admin/licenses/{license_id}/history', path(id))).data)
  }

  return {
    items,
    total,
    loading,
    failed,
    products,
    list,
    loadProducts,
    get,
    renew,
    setStatus,
    liftBlock,
    updateSettings,
    transfer,
    issueKey,
    usage,
    history,
  }
})
