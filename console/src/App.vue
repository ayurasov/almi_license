<script setup lang="ts">
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import { onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { onProblem } from '@/api/client'
import { userMessage } from '@/api/problem'
import { useSessionStore } from '@/stores/session'

const toast = useToast()
const router = useRouter()
const session = useSessionStore()
const { t, locale } = useI18n()

// Global handling of problem+json: a lost session goes to sign-in, field errors stay in the form,
// everything else is a toast with user_message.
const stop = onProblem((error) => {
  if (error.problem.status === 401) {
    session.forget()
    if (router.currentRoute.value.name !== 'login') {
      void router.push({ name: 'login', query: { next: router.currentRoute.value.fullPath } })
    }
    return
  }
  if (error.hasFieldErrors) return
  toast.add({
    severity: 'error',
    summary: userMessage(error.problem, locale.value) ?? t('errors.unknown'),
    detail: error.problem.request_id,
    life: 6000,
  })
})
onBeforeUnmount(stop)
</script>

<template>
  <Toast />
  <RouterView />
</template>
