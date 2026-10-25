import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { productApi } from '@/api/client'

import { answerName, useOfflineStore } from './offline'

const document = { format: 'alk-lic', version: 1, payload: 'a.b.c' } as const

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('useOfflineStore', () => {
  it('posts the request file and keeps the answer under the name given by the server', async () => {
    const response = new Response(null, { headers: { 'Content-Disposition': 'attachment; filename="i1.alk-lic"' } })
    const post = vi.spyOn(productApi, 'POST').mockResolvedValue({ data: document, response })
    const store = useOfflineStore()
    const answer = await store.process(new File(['{}'], 'device.alk-req'))
    expect(post).toHaveBeenCalledWith('/api/v1/offline/requests', expect.objectContaining({ body: { file: 'device.alk-req' } }))
    expect(answer).toEqual({ name: 'i1.alk-lic', document })
    expect(store.answer).toEqual(answer)
  })

  it('does not send a file over 64 KiB', async () => {
    const post = vi.spyOn(productApi, 'POST')
    const store = useOfflineStore()
    expect(await store.process(new File([new Uint8Array(64 * 1024 + 1)], 'big.alk-req'))).toBeNull()
    expect(store.tooLarge).toBe(true)
    expect(post).not.toHaveBeenCalled()
  })
})

describe('answerName', () => {
  it('falls back to the request name', () => {
    expect(answerName(null, 'pc-17.alk-req')).toBe('pc-17.alk-lic')
    expect(answerName('attachment', 'pc')).toBe('pc.alk-lic')
  })
})
