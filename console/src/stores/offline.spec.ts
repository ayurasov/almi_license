import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { productApi } from '@/api/client'
import { ApiError } from '@/api/problem'

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

describe('captcha (question 45)', () => {
  it('loads a captcha when the server asks and sends the answer with the next try', async () => {
    const problem = { type: 't', title: 't', status: 400, code: 'captcha_required' }
    const post = vi
      .spyOn(productApi, 'POST')
      .mockRejectedValueOnce(new ApiError(problem))
      .mockResolvedValueOnce({ data: document, response: new Response() })
    vi.spyOn(productApi, 'GET').mockResolvedValue({
      data: { captcha_id: 'c1', image: 'data:image/png;base64,AA', expires_at: '2026-11-02T08:10:00Z' },
      response: new Response(),
    })
    const store = useOfflineStore()
    const file = new File(['{}'], 'pc.alk-req')
    await expect(store.process(file)).rejects.toBeInstanceOf(ApiError)
    expect(store.captcha?.captcha_id).toBe('c1')
    await store.process(file, 'ACE34')
    const form = (post.mock.calls[1]?.[1] as unknown as { bodySerializer: () => FormData }).bodySerializer()
    expect(form.get('captcha_id')).toBe('c1')
    expect(form.get('captcha_answer')).toBe('ACE34')
    expect(store.captcha).toBeNull()
  })
})

describe('answerName', () => {
  it('falls back to the request name', () => {
    expect(answerName(null, 'pc-17.alk-req')).toBe('pc-17.alk-lic')
    expect(answerName('attachment', 'pc')).toBe('pc.alk-lic')
  })
})
