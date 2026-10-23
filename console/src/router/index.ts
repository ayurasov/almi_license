import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import { useSessionStore } from '@/stores/session'

export const SECTIONS = [
  'customers',
  'licenses',
  'activations',
  'catalog',
  'profiles',
  'import',
  'stats',
  'audit',
  'users',
] as const

const sections: RouteRecordRaw[] = SECTIONS.filter((name) => name !== 'customers').map((name) => ({
  path: name,
  name,
  component: () => import('@/views/SectionPlaceholder.vue'),
  props: { section: name },
}))

export const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', redirect: { name: 'customers' } },
      { path: 'customers', name: 'customers', component: () => import('@/views/CustomersView.vue') },
      ...sections,
    ],
  },
]

export const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  const session = useSessionStore()
  if (!session.checked) await session.load()
  return session.user ? true : { name: 'login', query: { next: to.fullPath } }
})
