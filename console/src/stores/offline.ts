import { defineStore } from 'pinia'
import { ref } from 'vue'

import { productApi } from '@/api/client'
import type { components } from '@/api/generated/product'
import { NetworkError } from '@/api/problem'

export type AlkFile = components['schemas']['AlkFile']

export interface OfflineAnswer {
  name: string
  document: AlkFile
}

const MAX_FILE_BYTES = 64 * 1024

/** The answer file is named by the server (Content-Disposition), otherwise after the request. */
export function answerName(disposition: string | null, requestName: string): string {
  const match = /filename="([^"]+)"/.exec(disposition ?? '')
  return match?.[1] ?? requestName.replace(/\.alk-req$/, '') + '.alk-lic'
}

/** Public offline activation portal (E08-02): .alk-req in, .alk-lic out, no session. */
export const useOfflineStore = defineStore('offline', () => {
  const answer = ref<OfflineAnswer | null>(null)
  const tooLarge = ref(false)

  async function process(file: File): Promise<OfflineAnswer | null> {
    answer.value = null
    tooLarge.value = file.size > MAX_FILE_BYTES
    if (tooLarge.value) return null
    const form = new FormData()
    form.append('file', file)
    const { data, response } = await productApi.POST('/api/v1/offline/requests', {
      body: { file: file.name },
      bodySerializer: () => form,
    })
    if (!data) throw new NetworkError('empty response')
    answer.value = { name: answerName(response.headers.get('Content-Disposition'), file.name), document: data }
    return answer.value
  }

  return { answer, tooLarge, process }
})
