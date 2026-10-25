<script setup lang="ts">
import Button from 'primevue/button'
import Card from 'primevue/card'
import Message from 'primevue/message'
import Password from 'primevue/password'
import { useToast } from 'primevue/usetoast'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, userMessage } from '@/api/problem'
import { useSessionStore } from '@/stores/session'

// The user's own password (question 31); required while the issued password is temporary.
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const toast = useToast()
const session = useSessionStore()
const current = ref('')
const next = ref('')
const repeat = ref('')
const fields = ref<Record<string, string[]>>({})
const error = ref('')
const busy = ref(false)
const required = computed(() => session.user?.must_change_password === true)

async function submit(): Promise<void> {
  fields.value = {}
  error.value = ''
  if (next.value !== repeat.value) {
    fields.value = { repeat: [t('password.mismatch')] }
    return
  }
  busy.value = true
  try {
    await session.changePassword(current.value, next.value)
    toast.add({ severity: 'success', summary: t('password.done'), life: 3000 })
    const target = typeof route.query.next === 'string' ? route.query.next : '/'
    await router.push(target)
  } catch (failure) {
    if (failure instanceof ApiError && failure.hasFieldErrors) fields.value = failure.fieldErrors
    else
      error.value =
        failure instanceof ApiError ? (userMessage(failure.problem, locale.value) ?? t('errors.unknown')) : t('errors.network')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="password-page">
    <Card class="password-card">
      <template #title>
        <h1 class="password-title">
          {{ t('password.title') }}
        </h1>
      </template>
      <template #content>
        <form
          class="password-form"
          @submit.prevent="submit"
        >
          <Message
            v-if="required"
            severity="warn"
            data-testid="password-required"
          >
            {{ t('password.required') }}
          </Message>
          <label for="current-password">{{ t('password.current') }}</label>
          <Password
            v-model="current"
            input-id="current-password"
            :feedback="false"
            toggle-mask
            autocomplete="current-password"
          />
          <small
            v-for="text in fields.current_password ?? []"
            :key="text"
            class="field-error"
          >{{ text }}</small>
          <label for="new-password">{{ t('password.next') }}</label>
          <Password
            v-model="next"
            input-id="new-password"
            :feedback="false"
            toggle-mask
            autocomplete="new-password"
          />
          <small class="hint">{{ t('password.rules') }}</small>
          <small
            v-for="text in fields.new_password ?? []"
            :key="text"
            class="field-error"
            data-testid="new-password-error"
          >{{ text }}</small>
          <label for="repeat-password">{{ t('password.repeat') }}</label>
          <Password
            v-model="repeat"
            input-id="repeat-password"
            :feedback="false"
            toggle-mask
            autocomplete="new-password"
          />
          <small
            v-for="text in fields.repeat ?? []"
            :key="text"
            class="field-error"
          >{{ text }}</small>
          <Message
            v-if="error"
            severity="error"
          >
            {{ error }}
          </Message>
          <Button
            type="submit"
            :label="t('password.submit')"
            :loading="busy"
            data-testid="password-submit"
          />
        </form>
      </template>
    </Card>
  </div>
</template>

<style scoped>
.password-page {
  display: grid;
  place-items: center;
  min-height: 100vh;
  padding: 1rem;
}
.password-card {
  max-width: 28rem;
}
.password-title {
  margin: 0;
  font-size: inherit;
}
.password-form {
  display: grid;
  gap: 0.5rem;
}
.field-error {
  color: var(--p-red-500);
}
.hint {
  color: var(--p-text-muted-color);
}
</style>
