import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'
import { ApiError, NetworkError } from '@/api/problem'

import { DEFAULT_QUERY, useCustomersStore } from './customers'

const customer = {
  id: '6f1c2a4e-8b3d-4c5f-9e7a-1b2c3d4e5f60',
  name: 'ООО «Ромашка»',
  inn: '7707083893',
  external_id: '',
  status: 'active' as const,
  created_at: '2026-11-02T08:15:00Z',
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useCustomersStore', () => {
  it('lists a page with filters, sorting and paging as query parameters', async () => {
    const get = vi.spyOn(api, 'GET').mockResolvedValue({
      data: { count: 41, results: [customer] },
      response: new Response(),
    })
    const store = useCustomersStore()

    await store.list({ ...DEFAULT_QUERY, page: 3, pageSize: 10, ordering: '-inn', name: 'ром', status: 'active' })

    expect(get).toHaveBeenCalledWith('/api/admin/customers', {
      params: {
        query: { page: 3, page_size: 10, ordering: '-inn', name: 'ром', inn: undefined, status: 'active' },
      },
    })
    expect(store.items).toEqual([customer])
    expect(store.total).toBe(41)
    expect(store.loading).toBe(false)
    expect(store.failed).toBeNull()
  })

  it('remembers a network failure and clears the table', async () => {
    vi.spyOn(api, 'GET').mockRejectedValue(new NetworkError())
    const store = useCustomersStore()

    await store.list(DEFAULT_QUERY)

    expect(store.failed).toBe('network')
    expect(store.items).toEqual([])
  })

  it('gets, creates and updates through the generated client', async () => {
    vi.spyOn(api, 'GET').mockResolvedValue({ data: customer, response: new Response() })
    const post = vi.spyOn(api, 'POST').mockResolvedValue({ data: customer, response: new Response() })
    const patch = vi.spyOn(api, 'PATCH').mockResolvedValue({ data: customer, response: new Response() })
    const store = useCustomersStore()

    expect(await store.get(customer.id)).toEqual(customer)
    expect(await store.create({ name: customer.name, inn: customer.inn })).toEqual(customer)
    expect(await store.update(customer.id, { status: 'archived' })).toEqual(customer)

    expect(post).toHaveBeenCalledWith('/api/admin/customers', { body: { name: customer.name, inn: customer.inn } })
    expect(patch).toHaveBeenCalledWith('/api/admin/customers/{customer_id}', {
      params: { path: { customer_id: customer.id } },
      body: { status: 'archived' },
    })
  })

  it('passes field errors of the server to the form', async () => {
    const problem = { type: 't', title: 't', status: 400, code: 'invalid_request', data: { fields: { inn: ['x'] } } }
    vi.spyOn(api, 'POST').mockRejectedValue(new ApiError(problem))
    const store = useCustomersStore()

    await expect(store.create({ name: 'А', inn: '1' })).rejects.toMatchObject({ fieldErrors: { inn: ['x'] } })
  })
})
