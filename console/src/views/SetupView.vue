<script setup lang="ts">
// First-run wizard of a local server (E09-01): registration code, then the central server
// address (online) or files only. Files mode gives a request file to hand over to ALMI.
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import SelectButton from 'primevue/selectbutton'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api/problem'
import { useInstanceStore } from '@/stores/instance'
import { useLocalStore } from '@/stores/local'
import { download } from '@/stores/servers'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const router = useRouter()
const store = useLocalStore()
const session = useSessionStore()
const instance = useInstanceStore()
const code = ref('')
const exchange = ref<'online' | 'files'>('online')
const url = ref('https://license.alter-os.ru')
const errors = ref<Record<string, string[]>>({})
const busy = ref(false)
const outcome = ref<'file' | 'done' | null>(null)
const isAdmin = computed(() => session.user?.role === 'admin')
const exchanges = computed(() => [
  { value: 'online', label: t('setup.online') },
  { value: 'files', label: t('setup.files') },
])

onMounted(() => {
  if (isAdmin.value) void store.load()
})

async function submit(): Promise<void> {
  busy.value = true
  errors.value = {}
  try {
    const result = await store.setup(code.value, exchange.value === 'online' ? url.value : '')
    if (result.request_file) {
      download(`${result.status.server_id ?? 'server'}.alk-req`, result.request_file)
      outcome.value = 'file'
    } else {
      outcome.value = 'done'
      await instance.reload()
    }
  } catch (failure) {
    if (failure instanceof ApiError) {
      errors.value = failure.hasFieldErrors ? failure.fieldErrors : { form: [failure.message] }
    } else errors.value = { form: [t('errors.network')] }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="setup">
    <h1>{{ t('setup.title') }}</h1>
    <Message
      v-if="!isAdmin"
      severity="warn"
    >
      {{ t('setup.adminOnly') }}
    </Message>
    <template v-else>
      <p>{{ t('setup.intro') }}</p>
      <Message
        v-for="text in errors.form ?? []"
        :key="text"
        severity="error"
      >
        {{ text }}
      </Message>
      <Message
        v-if="outcome === 'file'"
        severity="info"
        data-testid="setup-file-ready"
      >
        {{ t('setup.fileReady') }}
        <Button
          :label="t('setup.toPackage')"
          text
          @click="router.push({ name: 'package' })"
        />
      </Message>
      <Message
        v-if="outcome === 'done'"
        severity="success"
        data-testid="setup-done"
      >
        {{ t('setup.done') }}
      </Message>
      <form
        class="form"
        @submit.prevent="submit"
      >
        <label for="setup-code">{{ t('setup.code') }}</label>
        <InputText
          id="setup-code"
          v-model="code"
          autocomplete="off"
          :invalid="!!errors.registration_code"
          data-testid="setup-code"
        />
        <small
          v-for="text in errors.registration_code ?? []"
          :key="text"
          class="error"
        >{{ text }}</small>
        <span>{{ t('setup.exchange') }}</span>
        <SelectButton
          v-model="exchange"
          :options="exchanges"
          option-label="label"
          option-value="value"
          :allow-empty="false"
          data-testid="setup-exchange"
        />
        <template v-if="exchange === 'online'">
          <label for="setup-url">{{ t('setup.url') }}</label>
          <InputText
            id="setup-url"
            v-model="url"
            :invalid="!!errors.central_url"
          />
          <small
            v-for="text in errors.central_url ?? []"
            :key="text"
            class="error"
          >{{ text }}</small>
        </template>
        <Button
          type="submit"
          :label="t('setup.submit')"
          :loading="busy"
          data-testid="setup-submit"
        />
      </form>
    </template>
  </section>
</template>

<style scoped>
.setup {
  max-width: 40rem;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.error {
  color: var(--p-red-500);
}
</style>
