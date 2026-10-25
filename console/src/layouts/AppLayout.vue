<script setup lang="ts">
import Button from 'primevue/button'
import Menu from 'primevue/menu'
import type { MenuItem } from 'primevue/menuitem'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { canOpen } from '@/lib/roles'
import { SECTIONS } from '@/router'
import { useInstanceStore } from '@/stores/instance'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const router = useRouter()
const session = useSessionStore()
const instance = useInstanceStore()

// Sections by role (E07-08, E07-09); the server checks the same rights.
const items = computed<MenuItem[]>(() =>
  SECTIONS.filter((name) => canOpen(session.user?.role, name) && instance.allows(name)).map((name) => ({
    label: t(`menu.${name}`),
    command: () => void router.push({ name }),
  })),
)

async function signOut(): Promise<void> {
  await session.signOut()
  await router.push({ name: 'login' })
}

function toggleTheme(): void {
  document.documentElement.classList.toggle('app-dark')
}
</script>

<template>
  <div class="layout">
    <header class="layout-header">
      <strong>{{ t('app.title') }}</strong>
      <span class="layout-user">
        <Button
          icon="pi pi-moon"
          text
          rounded
          :aria-label="t('app.title')"
          @click="toggleTheme"
        />
        <span data-testid="current-user">{{ session.user?.username }}</span>
        <Button
          :label="t('app.signOut')"
          icon="pi pi-sign-out"
          text
          @click="signOut"
        />
      </span>
    </header>
    <aside class="layout-menu">
      <Menu :model="items" />
    </aside>
    <main class="layout-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template: 'header header' auto 'menu main' 1fr / 14rem 1fr;
  min-height: 100vh;
}
.layout-header {
  grid-area: header;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem;
  border-bottom: 1px solid var(--p-content-border-color);
}
.layout-user {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.layout-menu {
  grid-area: menu;
  padding: 0.5rem;
}
.layout-main {
  grid-area: main;
  padding: 1rem;
}
</style>
