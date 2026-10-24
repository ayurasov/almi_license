// Mode of this server (E09-01): a local server has no catalog, profiles or LK import of its own.
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'

export type Instance = components['schemas']['Instance']

// Sections served by the central server only; on a local server they come with the package.
export const CENTRAL_SECTIONS = new Set(['catalog', 'profiles', 'import', 'servers'])
// Sections of a local server only: its package and the first-run wizard.
export const LOCAL_SECTIONS = new Set(['package', 'setup'])

export const useInstanceStore = defineStore('instance', () => {
  const instance = ref<Instance | null>(null)
  const local = computed(() => instance.value?.mode === 'local')

  async function load(): Promise<Instance | null> {
    if (instance.value) return instance.value
    const { data } = await api.GET('/api/admin/instance')
    instance.value = data ?? null
    return instance.value
  }

  function allows(section: string): boolean {
    return local.value ? !CENTRAL_SECTIONS.has(section) : !LOCAL_SECTIONS.has(section)
  }

  /** After the wizard or a package upload the server is registered: ask again. */
  async function reload(): Promise<Instance | null> {
    instance.value = null
    return load()
  }

  return { instance, local, load, reload, allows }
})
