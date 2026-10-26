import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import { canOpen } from '@/lib/roles'
import { useInstanceStore } from '@/stores/instance'
import { useSessionStore } from '@/stores/session'

export const SECTIONS = [
  'overview',
  'customers',
  'licenses',
  'activations',
  'catalog',
  'profiles',
  'import',
  'stats',
  'audit',
  'users',
  'servers',
  'package',
] as const

export interface MenuItem {
  name: (typeof SECTIONS)[number]
  icon: string
}

// The side menu: sections in groups by the work of an operator (console/docs/design.md).
export const MENU: { key: string; items: MenuItem[] }[] = [
  { key: 'main', items: [{ name: 'overview', icon: 'pi-th-large' }] },
  {
    key: 'licensing',
    items: [
      { name: 'customers', icon: 'pi-building' },
      { name: 'licenses', icon: 'pi-key' },
      { name: 'activations', icon: 'pi-desktop' },
      { name: 'import', icon: 'pi-upload' },
    ],
  },
  {
    key: 'reference',
    items: [
      { name: 'catalog', icon: 'pi-box' },
      { name: 'profiles', icon: 'pi-sliders-h' },
    ],
  },
  {
    key: 'control',
    items: [
      { name: 'stats', icon: 'pi-chart-bar' },
      { name: 'audit', icon: 'pi-history' },
    ],
  },
  {
    key: 'admin',
    items: [
      { name: 'servers', icon: 'pi-server' },
      { name: 'package', icon: 'pi-inbox' },
      { name: 'users', icon: 'pi-users' },
    ],
  },
]

// Sections without their screen yet show a placeholder.
const READY = new Set(['overview', 'customers', 'licenses', 'activations', 'catalog', 'profiles', 'import', 'users', 'servers', 'package', 'stats', 'audit'])
const sections: RouteRecordRaw[] = SECTIONS.filter((name) => !READY.has(name)).map((name) => ({
  path: name,
  name,
  component: () => import('@/views/SectionPlaceholder.vue'),
  props: { section: name },
}))

export const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  // Outside the layout: a temporary password is changed before anything else (question 31).
  { path: '/password', name: 'password', component: () => import('@/views/PasswordView.vue') },
  { path: '/offline', name: 'offline', component: () => import('@/views/OfflinePortalView.vue'), meta: { public: true } },
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', redirect: { name: 'overview' } },
      { path: 'overview', name: 'overview', component: () => import('@/views/OverviewView.vue') },
      { path: 'customers', name: 'customers', component: () => import('@/views/CustomersView.vue') },
      { path: 'licenses', name: 'licenses', component: () => import('@/views/LicensesView.vue') },
      { path: 'licenses/:id', name: 'license', component: () => import('@/views/LicenseCardView.vue') },
      { path: 'activations', name: 'activations', component: () => import('@/views/ActivationsView.vue') },
      { path: 'catalog', name: 'catalog', component: () => import('@/views/CatalogView.vue') },
      { path: 'profiles', name: 'profiles', component: () => import('@/views/ProfilesView.vue') },
      { path: 'import', name: 'import', component: () => import('@/views/ImportView.vue') },
      { path: 'stats', name: 'stats', component: () => import('@/views/StatsView.vue') },
      { path: 'audit', name: 'audit', component: () => import('@/views/AuditView.vue') },
      { path: 'package', name: 'package', component: () => import('@/views/PackageView.vue') },
      { path: 'setup', name: 'setup', component: () => import('@/views/SetupView.vue') },
      { path: 'servers', name: 'servers', component: () => import('@/views/ServersView.vue') },
      { path: 'users', name: 'users', component: () => import('@/views/UsersView.vue') },
      ...sections,
    ],
  },
]

export const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  const session = useSessionStore()
  if (!session.checked) await session.load()
  if (!session.user) return { name: 'login', query: { next: to.fullPath } }
  if (to.name === 'password') return true
  if (session.user.must_change_password) return { name: 'password', query: { next: to.fullPath } }
  const instance = useInstanceStore()
  await instance.load()
  // A local server works only after the first-run wizard (E09-01).
  if (instance.instance?.setup_required && to.name !== 'setup' && to.name !== 'package') return { name: 'setup' }
  if (typeof to.name !== 'string') return true
  return instance.allows(to.name) && canOpen(session.user.role, to.name) ? true : { name: 'licenses' }
})
