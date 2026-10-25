<script setup lang="ts">
import Card from 'primevue/card'
import Message from 'primevue/message'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, userMessage } from '@/api/problem'
import { download } from '@/stores/servers'
import { useOfflineStore } from '@/stores/offline'

// Public page without sign-in (E08-02): the file is signed by the device key, the server limits
// the files per address (section 4.7 of document 2).
const { t, locale } = useI18n()
const store = useOfflineStore()
const error = ref('')
const busy = ref(false)

async function choose(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  busy.value = true
  error.value = ''
  try {
    const answer = await store.process(file)
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
            class="p-button"
            :class="{ 'p-disabled': busy }"
            for="offline-file"
          >{{ t('offline.choose') }}</label>
          <input
            id="offline-file"
            class="hidden"
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
  place-items: center;
  min-height: 100vh;
  padding: 1rem;
}
.portal-card {
  max-width: 36rem;
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
</style>
