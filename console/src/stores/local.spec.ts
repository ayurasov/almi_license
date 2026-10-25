import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'

import { type LocalStatus, useLocalStore } from './local'

const status: LocalStatus = {
  configured: true,
  registered: false,
  server_id: 'srv_01JABF8Q4W2N8C1R7ZB0Y5K6M3',
  exchange: 'files',
  central_url: '',
  customer_id: null,
  package_seq: 0,
  package_issued_at: null,
  package_valid_until: null,
  package_expires_soon: false,
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useLocalStore', () => {
  it('runs the wizard in files mode and keeps the status', async () => {
    const requestFile = { format: 'alk-req', version: 1, payload: 'a.b.c' }
    const post = vi.spyOn(api, 'POST').mockResolvedValue({
      data: { status, request_file: requestFile },
      response: new Response(),
    })
    const store = useLocalStore()

    const result = await store.setup('AAAAA-BBBBB', '')

    expect(post).toHaveBeenCalledWith('/api/admin/setup', {
      body: { registration_code: 'AAAAA-BBBBB', central_url: '' },
    })
    expect(result.request_file).toEqual(requestFile)
    expect(store.status).toEqual(status)
  })

  it('asks the central server for a newer package', async () => {
    const post = vi.spyOn(api, 'POST').mockResolvedValue({
      data: { ...status, registered: true, package_seq: 2 },
      response: new Response(),
    })
    const store = useLocalStore()
    expect((await store.sync()).package_seq).toBe(2)
    expect(post).toHaveBeenCalledWith('/api/admin/package/sync')
  })
})
