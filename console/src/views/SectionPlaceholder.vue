<script setup lang="ts">
import Message from 'primevue/message'
import { useI18n } from 'vue-i18n'

defineProps<{ section: string }>()
const { t } = useI18n()
</script>

<template>
  <h1>{{ t(`menu.${section}`) }}</h1>
  <Message severity="info">
    {{ t('placeholder') }}
  </Message>
</template>
