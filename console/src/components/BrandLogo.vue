<script setup lang="ts">
// The mark and the name of the console: «АЛицензия», the licence server of АЛМИ and АльтерСофт.
import { useI18n } from 'vue-i18n'

import BrandMark from '@/components/BrandMark.vue'

withDefaults(defineProps<{ size?: number; subtitle?: string }>(), { size: 32, subtitle: undefined })
const { t } = useI18n()
</script>

<template>
  <div class="brand">
    <BrandMark :size="size" />
    <div class="brand-text">
      <strong class="brand-name">{{ t('app.name') }}</strong>
      <span class="brand-subtitle">{{ subtitle ?? t('app.subtitle') }}</span>
    </div>
  </div>
</template>

<style scoped>
.brand {
  display: flex;
  gap: 0.6rem;
  align-items: center;
}
.brand-text {
  display: grid;
  line-height: 1.2;
}
.brand-name {
  font-size: 1.05rem;
  font-weight: 700;
}
.brand-subtitle {
  font-size: 0.78rem;
  color: var(--p-text-muted-color);
}
</style>
