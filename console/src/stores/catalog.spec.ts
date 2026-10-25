import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import { NetworkError } from '@/api/problem'

import { type ProductDetails, useCatalogStore } from './catalog'

const product: ProductDetails = {
  id: '6f1c2a4e-8b3d-4c5f-9e7a-1b2c3d4e5f60',
  code: 'alteroffice-desktop',
  name: { ru: 'АльтерОфис' },
  status: 'active',
  subject_type: 'device',
  default_metric_id: '6f1c2a4e-8b3d-4c5f-9e7a-1b2c3d4e5f61',
  default_profile_code: 'alteroffice-desktop.commercial',
  capabilities: [{ id: '6f1c2a4e-8b3d-4c5f-9e7a-1b2c3d4e5f62', code: 'view', status: 'active' }],
  editions: [],
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useCatalogStore', () => {
  it('loads products and metrics; a network failure is remembered', async () => {
    const get = vi.spyOn(api, 'GET').mockResolvedValue({ data: [], response: new Response() })
    const store = useCatalogStore()
    await store.load()
    expect(get.mock.calls.map((call) => call[0])).toEqual(['/api/admin/products', '/api/admin/catalog/metrics'])
    expect(store.failed).toBeNull()

    get.mockRejectedValue(new NetworkError())
    await store.load()
    expect(store.failed).toBe('network')
  })

  it('keeps the product the server returns after each change', async () => {
    const patch = vi.spyOn(api, 'PATCH').mockResolvedValue({
      data: { ...product, capabilities: product.capabilities.map((item) => ({ ...item, status: 'deprecated' as const })) },
      response: new Response(),
    })
    const post = vi.spyOn(api, 'POST').mockResolvedValue({ data: product, response: new Response() })
    const store = useCatalogStore()

    await store.setCapabilityStatus(product.id, 'view', 'deprecated')
    expect(patch).toHaveBeenCalledWith('/api/admin/catalog/products/{product_id}/capabilities/{code}', {
      params: { path: { product_id: product.id, code: 'view' } },
      body: { status: 'deprecated' },
    })
    expect(store.current?.capabilities[0]?.status).toBe('deprecated')

    await store.saveEdition(product.id, 'standard', { ru: 'Стандарт' }, ['view'])
    expect(post).toHaveBeenCalledWith('/api/admin/catalog/products/{product_id}/editions', {
      params: { path: { product_id: product.id } },
      body: { code: 'standard', name: { ru: 'Стандарт' }, base_capabilities: ['view'] },
    })
    expect(store.current).toEqual(product)
  })
})
