<script setup lang="ts">
import Button from 'primevue/button'
import Card from 'primevue/card'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Password from 'primevue/password'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, userMessage } from '@/api/problem'
import { useSessionStore } from '@/stores/session'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit(): Promise<void> {
  busy.value = true
  error.value = ''
  try {
    await session.signIn(username.value, password.value)
    const next = typeof route.query.next === 'string' ? route.query.next : '/'
    await router.push(next)
  } catch (failure) {
    error.value =
      failure instanceof ApiError ? (userMessage(failure.problem, locale.value) ?? t('errors.unknown')) : t('errors.network')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <Card>
      <template #title>
        {{ t('login.title') }}
      </template>
      <template #content>
        <form
          class="login-form"
          @submit.prevent="submit"
        >
          <label for="username">{{ t('login.username') }}</label>
          <InputText
            id="username"
            v-model="username"
            autocomplete="username"
          />
          <label for="password">{{ t('login.password') }}</label>
          <Password
            v-model="password"
            input-id="password"
            :feedback="false"
            toggle-mask
            autocomplete="current-password"
          />
          <Message
            v-if="error"
            severity="error"
            data-testid="login-error"
          >
            {{ error }}
          </Message>
          <Button
            type="submit"
            :label="t('login.submit')"
            :loading="busy"
          />
        </form>
      </template>
    </Card>
  </div>
</template>

<style scoped>
.login {
  display: grid;
  place-items: center;
  min-height: 100vh;
}
.login-form {
  display: grid;
  gap: 0.5rem;
  min-width: 20rem;
}
</style>
