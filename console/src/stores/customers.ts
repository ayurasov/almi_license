// Reference store (console/docs/reference-screen.md): one store per screen, methods
// list/get/create/update over the generated client; the view keeps no API calls of its own.
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { NetworkError } from '@/api/problem'

export type Customer = components['schemas']['Customer']
export type CustomerWrite = components['schemas']['CustomerWrite']

export interface CustomerQuery {
  page: number
  pageSize: number
  ordering: string
  name: string
  inn: string
  status: string
}

export const DEFAULT_QUERY: CustomerQuery = {
  page: 1,
  pageSize: 20,
  ordering: 'name',
  name: '',
  inn: '',
  status: '',
}

export const useCustomersStore = defineStore('customers', () => {
  const items = ref<Customer[]>([])
  const total = ref(0)
  const loading = ref(false)
  const failed = ref<'network' | 'server' | null>(null)

  async function list(query: CustomerQuery): Promise<void> {
    loading.value = true
    failed.value = null
    try {
      const { data } = await api.GET('/api/admin/customers', {
        params: {
          query: {
            page: query.page,
            page_size: query.pageSize,
            ordering: query.ordering,
            name: query.name || undefined,
            inn: query.inn || undefined,
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

  async function get(id: string): Promise<Customer> {
    const { data } = await api.GET('/api/admin/customers/{customer_id}', {
      params: { path: { customer_id: id } },
    })
    if (!data) throw new NetworkError('empty response')
    return data
  }

  async function create(values: CustomerWrite): Promise<Customer> {
    const { data } = await api.POST('/api/admin/customers', { body: values })
    if (!data) throw new NetworkError('empty response')
    return data
  }

  async function update(id: string, values: CustomerWrite): Promise<Customer> {
    const { data } = await api.PATCH('/api/admin/customers/{customer_id}', {
      params: { path: { customer_id: id } },
      body: values,
    })
    if (!data) throw new NetworkError('empty response')
    return data
  }

  return { items, total, loading, failed, list, get, create, update }
})
