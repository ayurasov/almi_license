<script setup lang="ts">
// Rights package of a local server (E09-03): state, upload of a .alk file, online update.
import Button from 'primevue/button'
import Message from 'primevue/message'
import { useToast } from 'primevue/usetoast'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/problem'
import { useInstanceStore } from '@/stores/instance'
import { useLocalStore } from '@/stores/local'

const { t, d } = useI18n()
const toast = useToast()
const store = useLocalStore()
const instance = useInstanceStore()
const errors = ref<string[]>([])
const busy = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

onMounted(() => {
  void store.load().catch(() => undefined)
})

async function run(action: () => Promise<unknown>, done: string): Promise<void> {
  busy.value = true
  errors.value = []
  const before = store.status?.package_seq ?? 0
  try {
    await action()
    const changed = (store.status?.package_seq ?? 0) > before
    toast.add({ severity: 'success', summary: changed ? done : t('packagePage.upToDate'), life: 3000 })
    await instance.reload()
  } catch (failure) {
    if (failure instanceof ApiError) {
      errors.value = failure.hasFieldErrors ? Object.values(failure.fieldErrors).flat() : [failure.message]
    } else errors.value = [t('errors.network')]
  } finally {
    busy.value = false
  }
}

async function onFile(event: Event): Promise<void> {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) await run(() => store.upload(file), t('packagePage.applied'))
  if (fileInput.value) fileInput.value.value = ''
}
</script>

<template>
  <section>
    <h1>{{ t('packagePage.title') }}</h1>
    <Message
      v-for="text in errors"
      :key="text"
      severity="error"
      data-testid="package-error"
    >
      {{ text }}
    </Message>
    <Message
      v-if="store.status?.package_expires_soon"
      severity="warn"
      :closable="false"
      data-testid="package-expires"
    >
      {{ t('packagePage.expiresSoon', { date: d(new Date(store.status.package_valid_until ?? '')) }) }}
    </Message>
    <dl
      v-if="store.status && store.status.package_seq > 0"
      class="state"
      data-testid="package-state"
    >
      <dt>{{ t('packagePage.server') }}</dt>
      <dd><code>{{ store.status.server_id }}</code></dd>
      <dt>{{ t('packagePage.exchange') }}</dt>
      <dd>{{ store.status.exchange === 'online' ? t('setup.online') : t('setup.files') }}</dd>
      <dt>{{ t('packagePage.seq') }}</dt>
      <dd data-testid="package-seq">
        {{ store.status.package_seq }}
      </dd>
      <dt>{{ t('packagePage.issued') }}</dt>
      <dd>{{ store.status.package_issued_at ? d(new Date(store.status.package_issued_at)) : '' }}</dd>
      <dt>{{ t('packagePage.validUntil') }}</dt>
      <dd>{{ store.status.package_valid_until ? d(new Date(store.status.package_valid_until)) : '' }}</dd>
    </dl>
    <p v-else>
      {{ t('packagePage.none') }}
    </p>
    <div class="actions">
      <label
        class="p-button"
        for="package-file"
      >{{ t('packagePage.upload') }}</label>
      <input
        id="package-file"
        ref="fileInput"
        class="hidden"
        type="file"
        accept=".alk,application/json"
        data-testid="package-file"
        @change="onFile"
      >
      <Button
        v-if="store.status?.exchange === 'online'"
        :label="t('packagePage.sync')"
        severity="secondary"
        :loading="busy"
        @click="run(() => store.sync(), t('packagePage.applied'))"
      />
    </div>
  </section>
</template>

<style scoped>
.state {
  display: grid;
  grid-template-columns: max-content auto;
  gap: 0.25rem 1rem;
}
.actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;
}
.hidden {
  display: none;
}
</style>
