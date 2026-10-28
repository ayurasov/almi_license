import { defineStore } from 'pinia'
import { ref } from 'vue'

import { productApi } from '@/api/client'
import type { components } from '@/api/generated/product'
import { ApiError, NetworkError } from '@/api/problem'

export type AlkFile = components['schemas']['AlkFile']

export interface Captcha {
  captcha_id: string
  image: string
}

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
  // After 5 files an hour the server asks for a captcha (question 45); one attempt per captcha.
  const captcha = ref<Captcha | null>(null)

  async function loadCaptcha(): Promise<void> {
    const { data } = await productApi.GET('/api/v1/offline/captcha')
    captcha.value = data ? { captcha_id: data.captcha_id, image: data.image } : null
  }

  async function process(file: File, captchaAnswer?: string): Promise<OfflineAnswer | null> {
    answer.value = null
    tooLarge.value = file.size > MAX_FILE_BYTES
    if (tooLarge.value) return null
    const form = new FormData()
    form.append('file', file)
    const used = captcha.value
    captcha.value = null
    if (used && captchaAnswer) {
      form.append('captcha_id', used.captcha_id)
      form.append('captcha_answer', captchaAnswer)
    }
    try {
      const { data, response } = await productApi.POST('/api/v1/offline/requests', {
        body: { file: file.name },
        bodySerializer: () => form,
      })
      if (!data) throw new NetworkError('empty response')
      answer.value = { name: answerName(response.headers.get('Content-Disposition'), file.name), document: data }
      return answer.value
    } catch (failure) {
      if (failure instanceof ApiError && failure.problem.code === 'captcha_required') await loadCaptcha()
      throw failure
    }
  }

  return { answer, tooLarge, captcha, loadCaptcha, process }
})
