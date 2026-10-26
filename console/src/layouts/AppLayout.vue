<script setup lang="ts">
import Button from 'primevue/button'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import BrandLogo from '@/components/BrandLogo.vue'
import BrandMark from '@/components/BrandMark.vue'
import { canOpen } from '@/lib/roles'
import { MENU } from '@/router'
import { useInstanceStore } from '@/stores/instance'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const instance = useInstanceStore()

// Sections by role (E07-08, E07-09) and by the mode of the server; the server checks the same rights.
const groups = computed(() =>
  MENU.map((group) => ({
    ...group,
    items: group.items.filter((item) => canOpen(session.user?.role, item.name) && instance.allows(item.name)),
  })).filter((group) => group.items.length > 0),
)

// The card of a licence belongs to the list of licences.
const current = computed(() => (route.name === 'license' ? 'licenses' : String(route.name ?? '')))

function readFlag(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

function saveFlag(key: string, value: boolean): void {
  try {
    localStorage.setItem(key, value ? '1' : '0')
  } catch {
    // Without storage the choice lasts until the page is reloaded.
  }
}

const collapsed = ref(readFlag('almi.menu.collapsed'))
const dark = ref(readFlag('almi.theme.dark'))
document.documentElement.classList.toggle('app-dark', dark.value)

function toggleMenu(): void {
  collapsed.value = !collapsed.value
  saveFlag('almi.menu.collapsed', collapsed.value)
}

function toggleTheme(): void {
  dark.value = !dark.value
  document.documentElement.classList.toggle('app-dark', dark.value)
  saveFlag('almi.theme.dark', dark.value)
}

const initials = computed(() => (session.user?.username ?? '?').slice(0, 2).toUpperCase())
const role = computed(() => (session.user ? t(`users.role.${session.user.role}`) : ''))
const mode = computed(() => (instance.local ? t('app.modeLocal') : t('app.modeCentral')))

async function signOut(): Promise<void> {
  await session.signOut()
  await router.push({ name: 'login' })
}
</script>

<template>
  <div
    class="layout"
    :class="{ collapsed }"
  >
    <aside class="sidebar">
      <RouterLink
        :to="{ name: 'overview' }"
        class="sidebar-brand"
      >
        <BrandMark
          v-if="collapsed"
          :size="32"
        />
        <BrandLogo
          v-else
          :subtitle="mode"
        />
      </RouterLink>

      <nav
        class="sidebar-nav"
        data-testid="main-menu"
      >
        <div
          v-for="group in groups"
          :key="group.key"
          class="nav-group"
        >
          <span
            v-if="group.key !== 'main'"
            class="nav-group-title"
          >{{ t(`menuGroups.${group.key}`) }}</span>
          <RouterLink
            v-for="item in group.items"
            :key="item.name"
            :to="{ name: item.name }"
            class="nav-item"
            :class="{ active: current === item.name }"
            :title="collapsed ? t(`menu.${item.name}`) : undefined"
            :data-testid="`menu-${item.name}`"
          >
            <i :class="['pi', item.icon]" />
            <span class="nav-label">{{ t(`menu.${item.name}`) }}</span>
          </RouterLink>
        </div>
      </nav>

      <div class="sidebar-footer">
        <div class="user">
          <span class="avatar">{{ initials }}</span>
          <span class="user-text">
            <strong data-testid="current-user">{{ session.user?.username }}</strong>
            <span class="muted">{{ role }}</span>
          </span>
        </div>
        <div class="footer-actions">
          <Button
            icon="pi pi-key"
            text
            rounded
            severity="secondary"
            :aria-label="t('password.open')"
            :title="t('password.open')"
            data-testid="change-password"
            @click="router.push({ name: 'password' })"
          />
          <Button
            :icon="dark ? 'pi pi-sun' : 'pi pi-moon'"
            text
            rounded
            severity="secondary"
            :aria-label="t('app.theme')"
            :title="t('app.theme')"
            @click="toggleTheme"
          />
          <Button
            :icon="collapsed ? 'pi pi-angle-double-right' : 'pi pi-angle-double-left'"
            text
            rounded
            severity="secondary"
            :aria-label="t('app.collapse')"
            :title="t('app.collapse')"
            @click="toggleMenu"
          />
          <Button
            icon="pi pi-sign-out"
            text
            rounded
            severity="secondary"
            :aria-label="t('app.signOut')"
            :title="t('app.signOut')"
            data-testid="sign-out"
            @click="signOut"
          />
        </div>
        <span class="vendor">{{ t('app.vendor') }}</span>
      </div>
    </aside>
    <main class="layout-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: var(--app-sidebar-width) 1fr;
  min-height: 100vh;
}
.layout.collapsed {
  grid-template-columns: 4.25rem 1fr;
}
.sidebar {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  height: 100vh;
  box-sizing: border-box;
  padding: 1rem 0.75rem;
  background: var(--app-shell);
  border-right: 1px solid var(--app-border);
  overflow-y: auto;
}
.sidebar-brand {
  padding: 0 0.4rem 1rem;
  color: inherit;
  text-decoration: none;
}
.sidebar-nav {
  flex: 1;
  display: grid;
  align-content: start;
  gap: 0.75rem;
}
.nav-group {
  display: grid;
  gap: 2px;
}
.nav-group-title {
  padding: 0 0.6rem 0.25rem;
  color: var(--p-text-muted-color);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.nav-item {
  display: flex;
  gap: 0.65rem;
  align-items: center;
  padding: 0.55rem 0.6rem;
  border-radius: 8px;
  color: var(--p-text-color);
  font-weight: 500;
  text-decoration: none;
}
.nav-item .pi {
  width: 1.1rem;
  color: var(--p-text-muted-color);
}
.nav-item:hover {
  background: var(--p-surface-100);
}
.app-dark .nav-item:hover {
  background: var(--p-surface-800);
}
.nav-item.active {
  background: var(--p-highlight-background);
  color: var(--p-primary-color);
}
.nav-item.active .pi {
  color: var(--p-primary-color);
}
.sidebar-footer {
  display: grid;
  gap: 0.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--app-border);
}
.user {
  display: flex;
  gap: 0.6rem;
  align-items: center;
  padding: 0 0.3rem;
}
.avatar {
  display: grid;
  place-items: center;
  flex: none;
  width: 2.1rem;
  height: 2.1rem;
  border-radius: 50%;
  background: var(--p-primary-color);
  color: var(--p-primary-contrast-color);
  font-size: 0.8rem;
  font-weight: 700;
}
.user-text {
  display: grid;
  line-height: 1.25;
  min-width: 0;
}
.user-text strong {
  overflow: hidden;
  text-overflow: ellipsis;
}
.user-text .muted {
  font-size: 0.8rem;
}
.footer-actions {
  display: flex;
  flex-wrap: wrap;
}
.vendor {
  padding: 0 0.3rem;
  color: var(--p-text-muted-color);
  font-size: 0.72rem;
}
.collapsed .nav-label,
.collapsed .nav-group-title,
.collapsed .user-text,
.collapsed .vendor {
  display: none;
}
.collapsed .nav-item {
  justify-content: center;
}
.collapsed .footer-actions {
  flex-direction: column;
  align-items: center;
}
.layout-main {
  min-width: 0;
  padding: 1.75rem 2.25rem 2.5rem;
}
</style>
