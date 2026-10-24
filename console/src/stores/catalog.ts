// Store of the Catalog screen (E07-06): products with editions and capabilities, metrics.
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { NetworkError } from '@/api/problem'

type Schemas = components['schemas']
export type ProductDetails = Schemas['ProductDetails']
export type ProductCreate = Schemas['ProductCreate']
export type ProductUpdate = Schemas['PatchedProductUpdate']
export type Metric = Schemas['Metric']
export type ProductSummary = Schemas['Product']

function required<T>(data: T | undefined): T {
  if (data === undefined) throw new NetworkError('empty response')
  return data
}

export const useCatalogStore = defineStore('catalog', () => {
  const products = ref<ProductSummary[]>([])
  const metrics = ref<Metric[]>([])
  const current = ref<ProductDetails | null>(null)
  const loading = ref(false)
  const failed = ref<'network' | 'server' | null>(null)

  async function load(): Promise<void> {
    loading.value = true
    failed.value = null
    try {
      const [list, metricList] = await Promise.all([
        api.GET('/api/admin/products'),
        api.GET('/api/admin/catalog/metrics'),
      ])
      products.value = list.data ?? []
      metrics.value = metricList.data ?? []
    } catch (error) {
      products.value = []
      failed.value = error instanceof NetworkError ? 'network' : 'server'
    } finally {
      loading.value = false
    }
  }

  function show(product: ProductDetails): ProductDetails {
    current.value = product
    return product
  }

  async function open(id: string): Promise<ProductDetails> {
    const { data } = await api.GET('/api/admin/catalog/products/{product_id}', {
      params: { path: { product_id: id } },
    })
    return show(required(data))
  }

  async function createProduct(values: ProductCreate): Promise<ProductDetails> {
    const { data } = await api.POST('/api/admin/catalog/products', { body: values })
    await load()
    return show(required(data))
  }

  async function updateProduct(id: string, values: ProductUpdate): Promise<ProductDetails> {
    const { data } = await api.PATCH('/api/admin/catalog/products/{product_id}', {
      params: { path: { product_id: id } },
      body: values,
    })
    return show(required(data))
  }

  async function addCapability(id: string, code: string, name: Record<string, string>): Promise<ProductDetails> {
    const { data } = await api.POST('/api/admin/catalog/products/{product_id}/capabilities', {
      params: { path: { product_id: id } },
      body: { code, name },
    })
    return show(required(data))
  }

  async function setCapabilityStatus(
    id: string,
    code: string,
    status: 'active' | 'deprecated',
  ): Promise<ProductDetails> {
    const { data } = await api.PATCH('/api/admin/catalog/products/{product_id}/capabilities/{code}', {
      params: { path: { product_id: id, code } },
      body: { status },
    })
    return show(required(data))
  }

  async function saveEdition(
    id: string,
    code: string,
    name: Record<string, string>,
    capabilities: string[],
  ): Promise<ProductDetails> {
    const { data } = await api.POST('/api/admin/catalog/products/{product_id}/editions', {
      params: { path: { product_id: id } },
      body: { code, name, base_capabilities: capabilities },
    })
    return show(required(data))
  }

  return {
    products,
    metrics,
    current,
    loading,
    failed,
    load,
    open,
    createProduct,
    updateProduct,
    addCapability,
    setCapabilityStatus,
    saveEdition,
  }
})
