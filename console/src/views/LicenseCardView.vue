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

import DirectiveDialog from '@/components/DirectiveDialog.vue'
import LicenseActionDialog from '@/components/LicenseActionDialog.vue'
import { licenseActions } from '@/lib/licenseActions'
import { canChange } from '@/lib/roles'
import { stateSeverity } from '@/lib/states'
import { type Activation, DEFAULT_ACTIVATION_QUERY, useActivationsStore } from '@/stores/activations'
import {
  type HistoryEvent,
  type License,
  type LicenseAction,
  type Usage,
  useLicensesStore,
} from '@/stores/licenses'
import { useInstanceStore } from '@/stores/instance'
import { useSessionStore } from '@/stores/session'

const { t, d } = useI18n()
const route = useRoute()
const store = useLicensesStore()
const session = useSessionStore()
const instance = useInstanceStore()
const activations = useActivationsStore()
const license = ref<License | null>(null)
const usage = ref<Usage | null>(null)
const history = ref<HistoryEvent[]>([])
const failed = ref(false)
const action = ref<LicenseAction | null>(null)
const actionOpen = ref(false)
const issuedKey = ref('')
const keyOpen = ref(false)
const directiveTarget = ref<{ kind: 'license'; id: string } | null>(null)

const id = computed(() => (typeof route.params.id === 'string' ? route.params.id : ''))
const ACTION_ICONS: Record<LicenseAction, string> = {
  renew: 'pi-calendar-plus',
  suspend: 'pi-pause',
  resume: 'pi-play',
  liftBlock: 'pi-unlock',
  settings: 'pi-sliders-h',
  transfer: 'pi-arrow-right-arrow-left',
  revoke: 'pi-ban',
}
const productName = computed(() => {
  const product = store.products.find((item) => item.id === license.value?.product_id)
  return product ? (product.name.ru ?? product.code) : ''
})
const actions = computed<LicenseAction[]>(() =>
  licenseActions(license.value?.status, canChange(session.user?.role), instance.local),
)

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
    <RouterLink
      :to="{ name: 'licenses' }"
      class="back"
    >
      <i class="pi pi-arrow-left" />
      {{ t('licenses.title') }}
    </RouterLink>
    <div class="toolbar card-head">
      <div class="title">
        <h1>{{ license.customer_name }}</h1>
        <span class="subtitle">
          <span>{{ productName }} · {{ t(`licenses.type.${license.type}`) }}</span>
          <Tag
            :value="t(`licenses.status.${license.status}`)"
            :severity="license.status === 'active' ? 'success' : 'warn'"
            data-testid="license-status"
          />
          <Tag
            v-if="license.state"
            :value="t(`licenses.state.${license.state}`)"
            :severity="stateSeverity(license.state)"
          />
        </span>
      </div>
    </div>
    <div
      v-if="actions.length > 0"
      class="actions"
    >
      <Button
        v-for="item in actions"
        :key="item"
        :label="t(`licenses.actions.${item}`)"
        :icon="`pi ${ACTION_ICONS[item]}`"
        :severity="item === 'revoke' ? 'danger' : 'secondary'"
        outlined
        :data-testid="`action-${item}`"
        @click="start(item)"
      />
      <Button
        :label="t('licenses.actions.directive')"
        icon="pi pi-send"
        data-testid="action-directive"
        @click="directiveTarget = { kind: 'license', id: license.id }"
      />
    </div>

    <Tabs
      value="params"
      class="panel"
    >
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
            <dt>{{ t('licenses.fields.maxVersion') }}</dt>
            <dd data-testid="max-version">
              {{ license.max_product_version || t('licenses.anyVersion') }}
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
            v-if="canChange(session.user?.role) && !instance.local"
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

    <DirectiveDialog
      :target="directiveTarget"
      @close="directiveTarget = null"
      @sent="directiveTarget = null"
    />
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
.back {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
  margin-bottom: 0.75rem;
  color: var(--p-text-muted-color);
  text-decoration: none;
}
.back:hover {
  color: var(--p-primary-color);
}
.card-head {
  margin-bottom: 1rem;
}
.title {
  display: grid;
  gap: 0.4rem;
}
.subtitle {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  color: var(--p-text-muted-color);
}
.actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 1.25rem;
}
.panel {
  padding: 0.25rem 1.25rem 1.25rem;
}
.fields {
  display: grid;
  grid-template-columns: max-content minmax(10rem, 1fr) max-content minmax(10rem, 1fr);
  gap: 0.7rem 1.5rem;
  margin: 0.5rem 0 0;
}
.fields dt {
  color: var(--p-text-muted-color);
}
.fields dd {
  margin: 0;
  font-weight: 500;
}
@media (max-width: 1000px) {
  .fields {
    grid-template-columns: max-content 1fr;
  }
}
.key {
  font-size: 1.4rem;
  letter-spacing: 0.1rem;
}
</style>
