// Store of the Import wizard (E07-07): preview of the LK export, article mapping, confirmation.
// The file stays in the browser: after a mapping change it is uploaded again for a new preview.
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { NetworkError } from '@/api/problem'

type Schemas = components['schemas']
export type ImportPreview = Schemas['ImportPreview']
export type ImportRow = Schemas['ImportRow']
export type ImportReport = Schemas['ImportReport']
export type ImportError = Schemas['ImportError']
export type ArticleMapping = Schemas['ArticleMapping']
export type ArticleMappingWrite = Schemas['ArticleMappingWrite']

function required<T>(data: T | undefined): T {
  if (data === undefined) throw new NetworkError('empty response')
  return data
}

export const useImportsStore = defineStore('imports', () => {
  const file = ref<File | null>(null)
  const preview = ref<ImportPreview | null>(null)
  const report = ref<ImportReport | null>(null)
  const mappings = ref<ArticleMapping[]>([])

  // AA codes of rows the catalog does not know yet (E06-02).
  const unmapped = computed(() => {
    const codes = new Set<string>()
    for (const row of preview.value?.rows ?? []) {
      const aa = row.fields.aa
      if (typeof aa === 'string' && row.fields.product === undefined) codes.add(aa)
    }
    return [...codes].sort()
  })

  async function upload(selected: File): Promise<ImportPreview> {
    const form = new FormData()
    form.append('file', selected)
    const { data } = await api.POST('/api/admin/imports', {
      // The generated type describes the form field; the body itself is multipart.
      body: { file: selected.name },
      bodySerializer: () => form,
    })
    file.value = selected
    preview.value = required(data)
    report.value = null
    return preview.value
  }

  async function recheck(): Promise<ImportPreview | null> {
    return file.value ? upload(file.value) : null
  }

  async function loadMappings(): Promise<void> {
    const { data } = await api.GET('/api/admin/article-mappings')
    mappings.value = data ?? []
  }

  async function saveMapping(aa: string, values: ArticleMappingWrite): Promise<ArticleMapping> {
    const { data } = await api.PUT('/api/admin/article-mappings/{aa}', {
      params: { path: { aa } },
      body: values,
    })
    const saved = required(data)
    mappings.value = [...mappings.value.filter((item) => item.aa !== aa), saved]
    return saved
  }

  async function apply(): Promise<ImportReport> {
    const session = preview.value?.session_id
    if (!session) throw new NetworkError('no preview')
    const { data } = await api.POST('/api/admin/imports/{session_id}/apply', {
      params: { path: { session_id: session } },
    })
    report.value = required(data)
    return report.value
  }

  function reset(): void {
    file.value = null
    preview.value = null
    report.value = null
  }

  return { file, preview, report, mappings, unmapped, upload, recheck, loadMappings, saveMapping, apply, reset }
})
