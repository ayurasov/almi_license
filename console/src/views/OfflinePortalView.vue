<script setup lang="ts">
import Button from 'primevue/button'
import Card from 'primevue/card'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, userMessage } from '@/api/problem'
import { download } from '@/stores/servers'
import { useOfflineStore } from '@/stores/offline'
import BrandLogo from '@/components/BrandLogo.vue'

// Public page without sign-in (E08-02): the file is signed by the device key, the server limits
// the files per address (section 4.7 of document 2).
const { t, locale } = useI18n()
const store = useOfflineStore()
const error = ref('')
const busy = ref(false)
const captchaAnswer = ref('')
// The file waits here while the user solves a captcha.
let pending: File | null = null

async function choose(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  pending = file
  await send()
}

async function send(): Promise<void> {
  if (!pending) return
  busy.value = true
  error.value = ''
  const answerText = captchaAnswer.value
  captchaAnswer.value = ''
  try {
    const answer = await store.process(pending, answerText)
    if (answer) download(answer.name, answer.document)
  } catch (failure) {
    error.value =
      failure instanceof ApiError ? (userMessage(failure.problem, locale.value) ?? t('errors.unknown')) : t('errors.network')
  } finally {
    busy.value = false
  }
}

function again(): void {
  if (store.answer) download(store.answer.name, store.answer.document)
}
</script>

<template>
  <div class="portal">
    <BrandLogo class="portal-logo" />
    <Card class="portal-card">
      <template #title>
        <h1 class="portal-title">
          {{ t('offline.title') }}
        </h1>
      </template>
      <template #content>
        <div class="portal-body">
          <p>{{ t('offline.intro') }}</p>
          <label
            class="dropzone portal-drop"
            :class="{ 'p-disabled': busy }"
            for="offline-file"
          >
            <i class="pi pi-file-import" />
            <strong>{{ t('offline.choose') }}</strong>
            <span class="muted">{{ t('offline.fileHint') }}</span>
          </label>
          <input
            id="offline-file"
            class="visually-hidden"
            type="file"
            accept=".alk-req,application/json"
            data-testid="offline-file"
            :disabled="busy"
            @change="choose"
          >
          <Message
            v-if="store.tooLarge"
            severity="warn"
            data-testid="offline-too-large"
          >
            {{ t('offline.tooLarge') }}
          </Message>
          <Message
            v-if="error"
            severity="error"
            data-testid="offline-error"
          >
            {{ error }}
          </Message>
          <form
            v-if="store.captcha"
            class="captcha"
            data-testid="offline-captcha"
            @submit.prevent="send"
          >
            <img
              :src="store.captcha.image"
              :alt="t('offline.captchaImage')"
              width="200"
              height="70"
            >
            <label for="captcha-answer">{{ t('offline.captchaAnswer') }}</label>
            <InputText
              id="captcha-answer"
              v-model="captchaAnswer"
              autocomplete="off"
              maxlength="16"
              data-testid="captcha-answer"
            />
            <div class="captcha-actions">
              <Button
                type="submit"
                :label="t('offline.captchaSend')"
                :loading="busy"
                data-testid="captcha-send"
              />
              <Button
                :label="t('offline.captchaOther')"
                severity="secondary"
                text
                @click="store.loadCaptcha"
              />
            </div>
          </form>
          <Message
            v-if="store.answer"
            severity="success"
            data-testid="offline-ready"
          >
            {{ t('offline.ready', { name: store.answer.name }) }}
            <a
              href="#"
              data-testid="offline-again"
              @click.prevent="again"
            >{{ t('offline.again') }}</a>
          </Message>
          <RouterLink :to="{ name: 'login' }">
            {{ t('offline.signIn') }}
          </RouterLink>
        </div>
      </template>
    </Card>
  </div>
</template>

<style scoped>
.portal {
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 1.5rem;
  min-height: 100vh;
  padding: 1rem;
  box-sizing: border-box;
  background: var(--app-shell);
}
.portal-card {
  max-width: 36rem;
  border: 1px solid var(--app-border);
  box-shadow: none;
}
.portal-drop {
  justify-self: stretch;
}
.portal-title {
  margin: 0;
  font-size: inherit;
}
.portal-body {
  display: grid;
  gap: 0.75rem;
  justify-items: start;
}
.hidden {
  display: none;
}
.captcha {
  display: grid;
  gap: 0.5rem;
  justify-items: start;
}
.captcha-actions {
  display: flex;
  gap: 0.5rem;
}
</style>
