import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/api/client'

import { type ImportPreview, useImportsStore } from './imports'

const preview: ImportPreview = {
  session_id: '6f1c2a4e-8b3d-4c5f-9e7a-1b2c3d4e5f60',
  filename: 'lk.xlsx',
  summary: { new: 1, update: 0, skip: 0, error: 2 },
  rows: [
    { row: 2, status: 'new', errors: [], fields: { aa: '01', product: 'alteroffice-desktop' } },
    { row: 3, status: 'error', errors: ['Артикул не сопоставлен: 77'], fields: { aa: '77' } },
    { row: 4, status: 'error', errors: ['Артикул не сопоставлен: 05'], fields: { aa: '05' } },
  ],
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useImportsStore', () => {
  it('uploads the file as multipart and lists unmapped articles', async () => {
    const seen: Request[] = []
    vi.stubGlobal('fetch', (request: Request) => {
      seen.push(request)
      return Promise.resolve(new Response(JSON.stringify(preview), { status: 201, headers: { 'Content-Type': 'application/json' } }))
    })
    const store = useImportsStore()

    await store.upload(new File(['xlsx'], 'lk.xlsx'))

    expect(seen[0]?.headers.get('Content-Type')).toMatch(/^multipart\/form-data; boundary=/)
    expect(store.unmapped).toEqual(['05', '77'])

    await store.recheck()
    expect(seen).toHaveLength(2)
  })

  it('saves a mapping and applies the session of the preview', async () => {
    const put = vi.spyOn(api, 'PUT').mockResolvedValue({
      data: { aa: '77', product_id: 'p', edition_id: null, metric_id: 'm' },
      response: new Response(),
    })
    const report = { session_id: preview.session_id, created: 1, updated: 0, skipped: 0, customers_created: 1, errors: [] }
    const post = vi.spyOn(api, 'POST').mockResolvedValue({ data: report, response: new Response() })
    const store = useImportsStore()
    store.preview = preview

    await store.saveMapping('77', { product_id: 'p', edition_id: null, metric_id: 'm' })
    expect(put).toHaveBeenCalledWith('/api/admin/article-mappings/{aa}', {
      params: { path: { aa: '77' } },
      body: { product_id: 'p', edition_id: null, metric_id: 'm' },
    })
    expect(store.mappings.map((m) => m.aa)).toEqual(['77'])

    expect(await store.apply()).toEqual(report)
    expect(post).toHaveBeenCalledWith('/api/admin/imports/{session_id}/apply', {
      params: { path: { session_id: preview.session_id } },
    })
  })
})
