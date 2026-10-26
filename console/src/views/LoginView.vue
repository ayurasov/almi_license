<script setup lang="ts">
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Password from 'primevue/password'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, userMessage } from '@/api/problem'
import BrandLogo from '@/components/BrandLogo.vue'
import BrandMark from '@/components/BrandMark.vue'
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
    <aside class="login-brand">
      <BrandMark :size="72" />
      <h2 class="login-name">
        {{ t('app.name') }}
      </h2>
      <p class="login-tagline">
        {{ t('login.tagline') }}
      </p>
      <ul class="login-points">
        <li><i class="pi pi-key" /> {{ t('login.points.licenses') }}</li>
        <li><i class="pi pi-desktop" /> {{ t('login.points.activations') }}</li>
        <li><i class="pi pi-server" /> {{ t('login.points.servers') }}</li>
      </ul>
      <span class="login-vendor">{{ t('app.vendor') }}</span>
    </aside>
    <main class="login-main">
      <form
        class="login-form"
        @submit.prevent="submit"
      >
        <BrandLogo class="login-logo" />
        <h1>{{ t('login.title') }}</h1>
        <label for="username">{{ t('login.username') }}</label>
        <InputText
          id="username"
          v-model="username"
          autocomplete="username"
          fluid
        />
        <label for="password">{{ t('login.password') }}</label>
        <Password
          v-model="password"
          input-id="password"
          :feedback="false"
          toggle-mask
          fluid
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
          fluid
        />
        <RouterLink
          :to="{ name: 'offline' }"
          class="login-offline"
        >
          <i class="pi pi-file-import" />
          {{ t('login.offline') }}
        </RouterLink>
      </form>
    </main>
  </div>
</template>

<style scoped>
.login {
  display: grid;
  grid-template-columns: minmax(20rem, 2fr) 3fr;
  min-height: 100vh;
}
.login-brand {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 1rem;
  padding: 3rem;
  background: linear-gradient(160deg, #e41c1c 0%, #a81414 100%);
  color: #fff;
}
.login-brand :deep(svg path:first-child) {
  fill: #fff;
}
.login-brand :deep(svg circle) {
  stroke: #e41c1c;
}
.login-brand :deep(svg path:last-child) {
  fill: #e41c1c;
}
.login-name {
  margin: 0;
  font-size: 2.2rem;
}
.login-tagline {
  max-width: 26rem;
  margin: 0;
  font-size: 1.1rem;
  line-height: 1.5;
  opacity: 0.92;
}
.login-points {
  display: grid;
  gap: 0.6rem;
  margin: 1rem 0 0;
  padding: 0;
  list-style: none;
}
.login-points .pi {
  margin-right: 0.5rem;
}
.login-vendor {
  margin-top: 2rem;
  font-size: 0.85rem;
  opacity: 0.8;
}
.login-main {
  display: grid;
  place-items: center;
  padding: 2rem;
}
.login-form {
  display: grid;
  gap: 0.6rem;
  width: min(24rem, 100%);
}
.login-logo {
  margin-bottom: 1.5rem;
}
.login-form h1 {
  margin-bottom: 0.75rem;
}
.login-form label {
  font-weight: 500;
}
.login-form .p-button {
  margin-top: 0.75rem;
}
.login-offline {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
  justify-content: center;
  margin-top: 0.5rem;
  color: var(--p-text-muted-color);
  text-decoration: none;
}
.login-offline:hover {
  color: var(--p-primary-color);
}
@media (max-width: 800px) {
  .login {
    grid-template-columns: 1fr;
  }
  .login-brand {
    display: none;
  }
}
</style>
