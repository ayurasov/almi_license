// The only API clients of the console: generated types (src/api/generated, npm run gen:api)
// and openapi-fetch (AGENTS.md, rule 14). Session cookie + CSRF token (E07-02). The Product API
// client is generated from the contract; the console uses only its public offline portal (E08-02).
import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from './generated/admin'
import type { paths as productPaths } from './generated/product'
import { ApiError, isProblem, NetworkError } from './problem'

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

export function csrfToken(cookies: string = document.cookie): string | undefined {
  for (const part of cookies.split(';')) {
    const [name, ...value] = part.trim().split('=')
    if (name === 'csrftoken') return decodeURIComponent(value.join('='))
  }
  return undefined
}

type ProblemListener = (error: ApiError) => void
const listeners = new Set<ProblemListener>()

/** Global handling of problems (toast, sign-in redirect); forms handle field errors themselves. */
export function onProblem(listener: ProblemListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

const middleware: Middleware = {
  onRequest({ request }) {
    if (!SAFE_METHODS.has(request.method)) {
      const token = csrfToken()
      if (token) request.headers.set('X-CSRFToken', token)
    }
    return request
  },
  async onResponse({ response }) {
    if (response.ok) return response
    const type = response.headers.get('Content-Type') ?? ''
    if (!type.includes('json')) throw new NetworkError(`HTTP ${String(response.status)}`)
    const body: unknown = await response.clone().json()
    if (!isProblem(body)) throw new NetworkError(`HTTP ${String(response.status)}`)
    const error = new ApiError(body)
    for (const listener of listeners) listener(error)
    throw error
  },
  // Also called for errors thrown by onResponse: keep those, wrap only transport failures.
  onError({ error }) {
    return error instanceof ApiError || error instanceof NetworkError ? error : new NetworkError()
  },
}

// Absolute base: Request() needs a full URL outside the browser (vitest).
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: 'same-origin',
  // Resolved per call, so tests can replace globalThis.fetch.
  fetch: (request) => globalThis.fetch(request),
})
api.use(middleware)

export const productApi = createClient<productPaths>({
  baseUrl: window.location.origin,
  credentials: 'same-origin',
  fetch: (request) => globalThis.fetch(request),
})
productApi.use(middleware)
