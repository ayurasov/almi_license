<script setup lang="ts">
// The first screen of the console: licences and seats at a glance, what needs the operator and
// the licences whose term ends soon. Data of the statistics (E10-01), no API of its own.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Message from 'primevue/message'
import ProgressBar from 'primevue/progressbar'
import Tag from 'primevue/tag'
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { daysLeft, expiring, needAttention, seatsTaken, statesInOrder } from '@/lib/overview'
import { canChange } from '@/lib/roles'
import { stateSeverity } from '@/lib/states'
import { useInstanceStore } from '@/stores/instance'
import { useLicensesStore } from '@/stores/licenses'
import { type LicenseStats, useStatsStore } from '@/stores/stats'
import { useSessionStore } from '@/stores/session'

const SOON_DAYS = 30

const { t, d } = useI18n()
const router = useRouter()
const store = useStatsStore()
const licenses = useLicensesStore()
const session = useSessionStore()
const instance = useInstanceStore()
// The moment of the screen; the server keeps its own clock for the licences themselves.
const now = new Date()

onMounted(() => {
  void store.load({ customerId: '', productId: '' })
  void licenses.loadProducts()
})

// Statistics name a product by its code; the catalog gives its name.
function productName(code: string): string {
  return licenses.products.find((product) => product.code === code)?.name.ru ?? code
}

const stats = computed(() => store.stats)
const soon = computed(() => expiring(stats.value?.rows ?? [], now, SOON_DAYS))
const states = computed(() => statesInOrder(stats.value?.by_state ?? {}))
const attention = computed(() => needAttention(stats.value?.by_state ?? {}))
const taken = computed(() => seatsTaken(stats.value?.active ?? 0, stats.value?.limit ?? 0))
const operator = computed(() => canChange(session.user?.role))

function open(row: LicenseStats): void {
  void router.push({ name: 'license', params: { id: row.license_id } })
}

function openLicenses(query: Record<string, string> = {}): void {
  void router.push({ name: 'licenses', query })
}
</script>

<template>
  <section>
    <div class="toolbar">
      <div class="title">
        <h1>{{ t('overview.title') }}</h1>
        <span class="muted">{{ t('overview.subtitle', { date: d(now, 'short') }) }}</span>
      </div>
      <div v-if="operator">
        <Button
          v-if="!instance.local"
          :label="t('overview.import')"
          icon="pi pi-upload"
          outlined
          @click="router.push({ name: 'import' })"
        />
        <Button
          :label="t('overview.licenses')"
          icon="pi pi-key"
          data-testid="overview-licenses"
          @click="openLicenses()"
        />
      </div>
    </div>

    <Message
      v-if="store.failed === 'network'"
      severity="error"
    >
      {{ t('errors.network') }}
    </Message>

    <div
      class="tiles"
      data-testid="overview-tiles"
    >
      <button
        type="button"
        class="tile"
        @click="openLicenses()"
      >
        <span class="tile-icon"><i class="pi pi-key" /></span>
        <span class="tile-label">{{ t('overview.tiles.licenses') }}</span>
        <strong class="tile-value">{{ stats?.licenses ?? '—' }}</strong>
        <span class="muted">{{ t('overview.tiles.customers', { count: new Set(stats?.rows.map((r) => r.customer_id)).size }) }}</span>
      </button>
      <div class="tile">
        <span class="tile-icon"><i class="pi pi-desktop" /></span>
        <span class="tile-label">{{ t('overview.tiles.seats') }}</span>
        <strong class="tile-value">{{ stats?.active ?? '—' }} <small class="muted">/ {{ stats?.limit ?? '—' }}</small></strong>
        <ProgressBar
          :value="taken"
          :show-value="false"
          class="tile-progress"
        />
      </div>
      <div class="tile">
        <span class="tile-icon"><i class="pi pi-check-circle" /></span>
        <span class="tile-label">{{ t('overview.tiles.free') }}</span>
        <strong class="tile-value">{{ stats?.free ?? '—' }}</strong>
        <span class="muted">{{ t('overview.tiles.reserve', { count: stats?.in_reserve ?? 0 }) }}</span>
      </div>
      <button
        type="button"
        class="tile"
        :class="{ alert: attention > 0 }"
        @click="openLicenses()"
      >
        <span class="tile-icon"><i class="pi pi-exclamation-triangle" /></span>
        <span class="tile-label">{{ t('overview.tiles.attention') }}</span>
        <strong class="tile-value">{{ attention }}</strong>
        <span class="muted">{{ t('overview.tiles.attentionHint') }}</span>
      </button>
    </div>

    <div class="columns">
      <div class="panel">
        <div class="panel-head">
          <h2>{{ t('overview.soon', { days: SOON_DAYS }) }}</h2>
          <Button
            :label="t('overview.all')"
            text
            icon="pi pi-arrow-right"
            icon-pos="right"
            @click="openLicenses({ ordering: 'valid_until' })"
          />
        </div>
        <DataTable
          :value="soon"
          :loading="store.loading"
          data-key="license_id"
          row-hover
          class="row-link"
          data-testid="overview-soon"
          @row-click="open($event.data as LicenseStats)"
        >
          <template #empty>
            {{ t('overview.noneSoon') }}
          </template>
          <Column
            field="customer_name"
            :header="t('stats.columns.customer')"
          />
          <Column :header="t('stats.columns.product')">
            <template #body="{ data }">
              {{ productName((data as LicenseStats).product) }}
            </template>
          </Column>
          <Column :header="t('licenses.columns.validUntil')">
            <template #body="{ data }">
              {{ d(new Date((data as LicenseStats).valid_until ?? ''), 'short') }}
            </template>
          </Column>
          <Column :header="t('overview.left')">
            <template #body="{ data }">
              <Tag
                :value="t('overview.days', { count: daysLeft((data as LicenseStats).valid_until ?? '', now) })"
                :severity="daysLeft((data as LicenseStats).valid_until ?? '', now) <= 7 ? 'danger' : 'warn'"
              />
            </template>
          </Column>
        </DataTable>
      </div>

      <div class="panel">
        <div class="panel-head">
          <h2>{{ t('overview.states') }}</h2>
        </div>
        <ul
          class="states"
          data-testid="overview-states"
        >
          <li
            v-for="item in states"
            :key="item.state"
          >
            <Tag
              :value="t(`licenses.state.${item.state}`)"
              :severity="stateSeverity(item.state)"
            />
            <strong>{{ item.count }}</strong>
          </li>
          <li
            v-if="states.length === 0"
            class="muted"
          >
            {{ t('stats.empty') }}
          </li>
        </ul>
        <div class="seen">
          <span class="muted">{{ t('stats.tiles.lastSeen') }}</span>
          <strong>{{ stats?.last_seen_at ? d(new Date(stats.last_seen_at), 'long') : t('stats.never') }}</strong>
        </div>
        <div class="seen">
          <span class="muted">{{ t('stats.tiles.auto') }}</span>
          <strong>{{ stats?.released_auto ?? 0 }}</strong>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.title {
  display: grid;
  gap: 0.25rem;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
}
.tile {
  display: grid;
  gap: 0.3rem;
  align-content: start;
  padding: 1.1rem 1.25rem;
  background: var(--p-content-background);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  color: inherit;
  font: inherit;
  text-align: left;
}
button.tile {
  cursor: pointer;
}
button.tile:hover {
  border-color: var(--p-primary-color);
}
.tile-icon {
  display: grid;
  place-items: center;
  width: 2.25rem;
  height: 2.25rem;
  margin-bottom: 0.35rem;
  border-radius: 8px;
  background: var(--p-highlight-background);
  color: var(--p-primary-color);
}
.tile-label {
  color: var(--p-text-muted-color);
  font-weight: 500;
}
.tile-value {
  font-size: 1.9rem;
  line-height: 1.1;
}
.tile-value small {
  font-size: 1rem;
  font-weight: 500;
}
.tile-progress {
  height: 0.45rem;
  margin-top: 0.35rem;
}
.tile.alert {
  border-color: var(--p-primary-200);
  background: var(--p-highlight-background);
}
.columns {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(16rem, 1fr);
  gap: 1rem;
  align-items: start;
}
.columns .panel + .panel {
  margin-top: 0;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}
.panel-head h2 {
  margin: 0;
}
.states {
  display: grid;
  gap: 0.6rem;
  margin: 0 0 1rem;
  padding: 0;
  list-style: none;
}
.states li {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.seen {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--app-border);
  margin-top: 0.6rem;
}
@media (max-width: 1100px) {
  .columns {
    grid-template-columns: 1fr;
  }
}
</style>
