<script setup lang="ts">
// License card (E07-04): parameters, keys, activations, history, usage; actions through
// LicenseActionDialog. Built from the parts of the reference screen (docs/reference-screen.md).
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import Tab from 'primevue/tab'
import TabList from 'primevue/tablist'
import TabPanel from 'primevue/tabpanel'
import TabPanels from 'primevue/tabpanels'
import Tabs from 'primevue/tabs'
import Tag from 'primevue/tag'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import LicenseActionDialog from '@/components/LicenseActionDialog.vue'
import { type Activation, DEFAULT_ACTIVATION_QUERY, useActivationsStore } from '@/stores/activations'
import {
  type HistoryEvent,
  type License,
  type LicenseAction,
  type Usage,
  useLicensesStore,
} from '@/stores/licenses'

const { t, d } = useI18n()
const route = useRoute()
const store = useLicensesStore()
const activations = useActivationsStore()
const license = ref<License | null>(null)
const usage = ref<Usage | null>(null)
const history = ref<HistoryEvent[]>([])
const failed = ref(false)
const action = ref<LicenseAction | null>(null)
const actionOpen = ref(false)
const issuedKey = ref('')
const keyOpen = ref(false)

const id = computed(() => (typeof route.params.id === 'string' ? route.params.id : ''))
const productName = computed(() => {
  const product = store.products.find((item) => item.id === license.value?.product_id)
  return product ? (product.name.ru ?? product.code) : ''
})
const actions = computed<LicenseAction[]>(() => {
  const status = license.value?.status
  if (status === 'revoked') return []
  return [
    'renew',
    status === 'suspended' ? 'resume' : 'suspend',
    'liftBlock',
    'settings',
    'transfer',
    'revoke',
  ]
})

const userLimit = computed(() => {
  const limits = license.value?.limits
  const value = limits?.named_users ?? limits?.active_users
  if (value === null || value === undefined) return '—'
  return limits?.only_count_active ? `${String(value)} (${t('licenses.onlyActive')})` : String(value)
})

// "3.2.0: 5, 3.3.0: 2"
function counts(values: Record<string, number>): string {
  return Object.entries(values)
    .map(([name, count]) => `${name}: ${String(count)}`)
    .join(', ')
}

function date(value: string | null | undefined, empty = '—'): string {
  return value ? d(new Date(value)) : empty
}

async function load(): Promise<void> {
  failed.value = false
  try {
    void store.loadProducts()
    license.value = await store.get(id.value)
    ;[usage.value, history.value] = await Promise.all([store.usage(id.value), store.history(id.value)])
    await activations.list({ ...DEFAULT_ACTIVATION_QUERY, licenseId: id.value, pageSize: 100 })
  } catch {
    failed.value = true
  }
}

watch(id, () => void load(), { immediate: true })

function start(next: LicenseAction): void {
  action.value = next
  actionOpen.value = true
}

async function issueKey(): Promise<void> {
  if (!license.value) return
  const issued = await store.issueKey(license.value.id)
  issuedKey.value = issued.key
  keyOpen.value = true
  await load()
}

function closeKey(): void {
  issuedKey.value = ''  // the key lives only in this dialog
  keyOpen.value = false
}
</script>

<template>
  <section v-if="license">
    <div class="toolbar">
      <h1>{{ license.customer_name }} — {{ productName }}</h1>
      <Tag
        :value="t(`licenses.status.${license.status}`)"
        :severity="license.status === 'active' ? 'success' : 'warn'"
        data-testid="license-status"
      />
    </div>
    <div class="actions">
      <Button
        v-for="item in actions"
        :key="item"
        :label="t(`licenses.actions.${item}`)"
        :severity="item === 'revoke' ? 'danger' : 'secondary'"
        :data-testid="`action-${item}`"
        @click="start(item)"
      />
    </div>

    <Tabs value="params">
      <TabList>
        <Tab value="params">
          {{ t('licenses.tabs.params') }}
        </Tab>
        <Tab value="keys">
          {{ t('licenses.tabs.keys') }}
        </Tab>
        <Tab value="activations">
          {{ t('licenses.tabs.activations') }}
        </Tab>
        <Tab value="history">
          {{ t('licenses.tabs.history') }}
        </Tab>
        <Tab value="usage">
          {{ t('licenses.tabs.usage') }}
        </Tab>
      </TabList>
      <TabPanels>
        <TabPanel value="params">
          <dl class="fields">
            <dt>{{ t('licenses.fields.type') }}</dt>
            <dd>{{ t(`licenses.type.${license.type}`) }}</dd>
            <dt>{{ t('licenses.fields.limit') }}</dt>
            <dd>{{ license.limit }}</dd>
            <dt>{{ t('licenses.fields.userLimit') }}</dt>
            <dd data-testid="user-limit">
              {{ userLimit }}
            </dd>
            <dt>{{ t('licenses.fields.reservePct') }}</dt>
            <dd>{{ license.reserve_pct ?? t('licenses.fromProfile') }}</dd>
            <dt>{{ t('licenses.fields.validFrom') }}</dt>
            <dd>{{ date(license.valid_from) }}</dd>
            <dt>{{ t('licenses.fields.validUntil') }}</dt>
            <dd>{{ date(license.valid_until, t('licenses.perpetual')) }}</dd>
            <dt>{{ t('licenses.fields.supportUntil') }}</dt>
            <dd>{{ date(license.support_until) }}</dd>
            <dt>{{ t('licenses.fields.enforcement') }}</dt>
            <dd>{{ t(`licenses.enforcement.${license.enforcement || 'profile'}`) }}</dd>
            <dt>{{ t('licenses.fields.monitorUntil') }}</dt>
            <dd>{{ date(license.monitor_until) }}</dd>
            <dt>{{ t('licenses.fields.rightsVersion') }}</dt>
            <dd>{{ license.rights_version }}</dd>
          </dl>
        </TabPanel>
        <TabPanel value="keys">
          <ul>
            <li
              v-for="mask in license.key_masks"
              :key="mask"
            >
              {{ mask }}
            </li>
          </ul>
          <p v-if="license.key_masks.length === 0">
            {{ t('licenses.key.empty') }}
          </p>
          <Button
            :label="t('licenses.actions.issueKey')"
            icon="pi pi-key"
            :disabled="license.status === 'revoked'"
            data-testid="issue-key"
            @click="issueKey"
          />
        </TabPanel>
        <TabPanel value="activations">
          <DataTable
            :value="activations.items"
            data-key="activation_id"
          >
            <template #empty>
              {{ t('activations.empty') }}
            </template>
            <Column
              field="activation_id"
              :header="t('activations.columns.id')"
            />
            <Column
              field="instance_name"
              :header="t('activations.columns.name')"
            />
            <Column
              field="product_version"
              :header="t('activations.columns.version')"
            />
            <Column :header="t('activations.columns.status')">
              <template #body="{ data }">
                {{ t(`activations.status.${(data as Activation).status}`) }}
              </template>
            </Column>
            <Column :header="t('activations.columns.lastSeen')">
              <template #body="{ data }">
                {{ date((data as Activation).last_seen_at) }}
              </template>
            </Column>
          </DataTable>
        </TabPanel>
        <TabPanel value="history">
          <DataTable
            :value="history"
            data-key="seq"
          >
            <template #empty>
              {{ t('licenses.history.empty') }}
            </template>
            <Column :header="t('licenses.history.at')">
              <template #body="{ data }">
                {{ date((data as HistoryEvent).at) }}
              </template>
            </Column>
            <Column
              field="actor"
              :header="t('licenses.history.actor')"
            />
            <Column
              field="action"
              :header="t('licenses.history.action')"
            />
          </DataTable>
        </TabPanel>
        <TabPanel value="usage">
          <dl
            v-if="usage"
            class="fields"
          >
            <dt>{{ t('licenses.usage.active') }}</dt>
            <dd data-testid="usage-active">
              {{ usage.active }} / {{ license.limit }}
            </dd>
            <dt>{{ t('licenses.usage.inReserve') }}</dt>
            <dd>{{ usage.in_reserve }}</dd>
            <dt>{{ t('licenses.usage.releasedAuto') }}</dt>
            <dd>{{ usage.released_auto }}</dd>
            <dt>{{ t('licenses.usage.conflicts') }}</dt>
            <dd>{{ usage.conflicts }}</dd>
            <dt>{{ t('licenses.usage.lastSeen') }}</dt>
            <dd>{{ date(usage.last_seen_at, t('licenses.usage.never')) }}</dd>
            <dt>{{ t('licenses.usage.byVersion') }}</dt>
            <dd>{{ counts(usage.by_version) }}</dd>
            <dt>{{ t('licenses.usage.byOs') }}</dt>
            <dd>{{ counts(usage.by_os) }}</dd>
          </dl>
        </TabPanel>
      </TabPanels>
    </Tabs>

    <LicenseActionDialog
      v-model:visible="actionOpen"
      :license="license"
      :action="action"
      @done="load"
    />

    <Dialog
      :visible="keyOpen"
      modal
      :closable="false"
      :header="t('licenses.key.title')"
    >
      <Message severity="warn">
        {{ t('licenses.key.once') }}
      </Message>
      <p class="key">
        <code data-testid="issued-key">{{ issuedKey }}</code>
      </p>
      <Button
        :label="t('licenses.key.close')"
        data-testid="issued-key-close"
        @click="closeKey"
      />
    </Dialog>
  </section>
  <Message
    v-else-if="failed"
    severity="error"
  >
    {{ t('errors.network') }}
    <Button
      :label="t('errors.retry')"
      text
      @click="load"
    />
  </Message>
</template>

<style scoped>
.toolbar,
.actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}
.actions {
  margin-bottom: 1rem;
}
.fields {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1rem;
}
.key {
  font-size: 1.4rem;
  letter-spacing: 0.1rem;
}
</style>
