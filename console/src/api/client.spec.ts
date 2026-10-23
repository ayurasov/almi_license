import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, csrfToken, onProblem } from './client'
import { ApiError, NetworkError } from './problem'

const problem = {
  type: 'https://license.alter-os.ru/problems/invalid_request',
  title: 'Нарушен формат запроса',
  status: 400,
  code: 'invalid_request',
  request_id: 'r1',
  data: { fields: { inn: ['Неверный ИНН'] } },
}

function reply(status: number, body: unknown, type = 'application/problem+json'): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': type } })
}

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
})

describe('api client', () => {
  it('reads the CSRF cookie', () => {
    expect(csrfToken('a=1; csrftoken=abc%3D; b=2')).toBe('abc=')
    expect(csrfToken('a=1')).toBeUndefined()
  })

  it('sends the CSRF token with writes only', async () => {
    document.cookie = 'csrftoken=token-1'
    const seen: Request[] = []
    vi.stubGlobal('fetch', (request: Request) => {
      seen.push(request)
      return Promise.resolve(reply(201, { ...problem, status: 201 }, 'application/json'))
    })

    await api.POST('/api/admin/customers', { body: { name: 'А' } })
    await api.GET('/api/admin/customers')

    const [write, read] = seen
    expect(write?.headers.get('X-CSRFToken')).toBe('token-1')
    expect(read?.headers.get('X-CSRFToken')).toBeNull()
  })

  it('turns problem+json into ApiError and tells the listeners', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(reply(400, problem))))
    const seen: ApiError[] = []
    const stop = onProblem((error) => seen.push(error))

    const failure: unknown = await api.GET('/api/admin/customers').catch((error: unknown) => error)
    stop()

    expect(failure).toBeInstanceOf(ApiError)
    expect((failure as ApiError).fieldErrors).toEqual({ inn: ['Неверный ИНН'] })
    expect(seen).toHaveLength(1)
  })

  it('reports a network failure or a non-problem answer as NetworkError', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('offline'))))
    await expect(api.GET('/api/admin/customers')).rejects.toBeInstanceOf(NetworkError)

    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('<html>', { status: 502 }))))
    await expect(api.GET('/api/admin/customers')).rejects.toBeInstanceOf(NetworkError)
  })
})
