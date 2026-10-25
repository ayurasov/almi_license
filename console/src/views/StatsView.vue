<script setup lang="ts">
// Statistics (E10-01, E10-02): totals and per-licence rows by customer and product, the spread by
// product version and OS, and the XLSX export of the same filter.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { canChange } from '@/lib/roles'
import { useSessionStore } from '@/stores/session'
import { type LicenseStats, useStatsStore } from '@/stores/stats'

type Option = { value: string; label: string }

// "520 / 500": users reported by server instances against the licence limit (E11-02)
function users(row: LicenseStats): string {
  const used = String(row.users ?? 0)
  return row.user_limit === null ? used : `${used} / ${String(row.user_limit)}`
}

const { t, d } = useI18n()
const store = useStatsStore()
const session = useSessionStore()
const filter = reactive({ customerId: '', productId: '' })
const customers = ref<Option[]>([])
const products = ref<Option[]>([])
const exporting = ref(false)

onMounted(async () => {
  void store.load(filter)
  // A customer viewer has no customer list (E07-08).
  const [customerList, productList] = await Promise.all([
    canChange(session.user?.role)
      ? api.GET('/api/admin/customers', { params: { query: { page_size: 100 } } })
      : Promise.resolve({ data: undefined }),
    api.GET('/api/admin/products'),
  ])
  customers.value = (customerList.data?.results ?? []).map((c: components['schemas']['Customer']) => ({
    value: c.id,
    label: c.name,
  }))
  products.value = (productList.data ?? []).map((p) => ({ value: p.id, label: p.code }))
})

const withAll = (options: Option[]) => [{ value: '', label: t('stats.all') }, ...options]
const tiles = computed(() => {
  const s = store.stats
  if (!s) return []
  return [
    { key: 'licenses', value: String(s.licenses) },
    { key: 'limit', value: String(s.limit) },
    { key: 'active', value: String(s.active) },
    { key: 'free', value: String(s.free) },
    { key: 'reserve', value: String(s.in_reserve) },
    { key: 'auto', value: String(s.released_auto) },
    { key: 'lastSeen', value: s.last_seen_at ? d(new Date(s.last_seen_at)) : t('stats.never') },
  ]
})
const spread = (values: Record<string, number> | undefined) =>
  Object.entries(values ?? {})
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)

async function exportXlsx(): Promise<void> {
  exporting.value = true
  try {
    const blob = await store.exportXlsx(filter)
    const url = URL.createObjectURL(blob)
    const link = Object.assign(document.createElement('a'), { href: url, download: 'almi-stats.xlsx' })
    link.click()
    URL.revokeObjectURL(url)
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <section>
    <div class="toolbar">
      <h1>{{ t('stats.title') }}</h1>
      <Button
        :label="t('stats.export')"
        icon="pi pi-file-excel"
        :loading="exporting"
        data-testid="stats-export"
        @click="exportXlsx"
      />
    </div>
    <div class="filters">
      <Select
        v-if="canChange(session.user?.role)"
        v-model="filter.customerId"
        :options="withAll(customers)"
        option-label="label"
        option-value="value"
        filter
        :placeholder="t('stats.customer')"
        :aria-label="t('stats.customer')"
        data-testid="stats-customer"
        @change="store.load(filter)"
      />
      <Select
        v-model="filter.productId"
        :options="withAll(products)"
        option-label="label"
        option-value="value"
        :placeholder="t('stats.product')"
        :aria-label="t('stats.product')"
        @change="store.load(filter)"
      />
    </div>
    <Message
      v-if="store.failed === 'network'"
      severity="error"
    >
      {{ t('errors.network') }}
    </Message>

    <div
      v-if="store.stats"
      class="tiles"
      data-testid="stats-tiles"
    >
      <div
        v-for="tile in tiles"
        :key="tile.key"
        class="tile"
        :data-testid="`tile-${tile.key}`"
      >
        <span class="value">{{ tile.value }}</span>
        <span class="label">{{ t(`stats.tiles.${tile.key}`) }}</span>
      </div>
    </div>

    <DataTable
      :value="store.stats?.rows ?? []"
      :loading="store.loading"
      data-key="license_id"
      paginator
      :rows="20"
      size="small"
      data-testid="stats-table"
    >
      <template #empty>
        {{ t('stats.empty') }}
      </template>
      <Column
        field="customer_name"
        :header="t('stats.columns.customer')"
        sortable
      />
      <Column
        field="product"
        :header="t('stats.columns.product')"
        sortable
      />
      <Column
        field="limit"
        :header="t('stats.columns.limit')"
        sortable
      />
      <Column
        field="active"
        :header="t('stats.columns.active')"
        sortable
      />
      <Column
        field="in_reserve"
        :header="t('stats.columns.reserve')"
      />
      <Column
        field="free"
        :header="t('stats.columns.free')"
        sortable
      />
      <Column
        field="released_auto"
        :header="t('stats.columns.auto')"
      />
      <Column
        field="local_active"
        :header="t('stats.columns.local')"
      />
      <Column :header="t('stats.columns.users')">
        <template #body="{ data }">
          <template v-if="(data as LicenseStats).users !== null">
            {{ users(data as LicenseStats) }}
            <Tag
              v-if="(data as LicenseStats).users_exceeded"
              :value="t('stats.usersExceeded')"
              severity="danger"
              data-testid="users-exceeded"
            />
          </template>
        </template>
      </Column>
      <Column :header="t('stats.columns.lastSeen')">
        <template #body="{ data }">
          {{ (data as LicenseStats).last_seen_at ? d(new Date((data as LicenseStats).last_seen_at ?? '')) : t('stats.never') }}
        </template>
      </Column>
    </DataTable>

    <div
      v-if="store.stats"
      class="spread"
    >
      <div>
        <h3>{{ t('stats.versions') }}</h3>
        <DataTable
          :value="spread(store.stats.by_version)"
          size="small"
          data-testid="stats-versions"
        >
          <Column field="name" />
          <Column field="count" />
        </DataTable>
      </div>
      <div>
        <h3>{{ t('stats.systems') }}</h3>
        <DataTable
          :value="spread(store.stats.by_os)"
          size="small"
        >
          <Column field="name" />
          <Column field="count" />
        </DataTable>
      </div>
    </div>
  </section>
</template>

<style scoped>
.toolbar,
.filters {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.toolbar {
  justify-content: space-between;
}
.filters {
  margin-bottom: 1rem;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.tile {
  display: flex;
  flex-direction: column;
  padding: 0.75rem;
  border: 1px solid var(--p-content-border-color);
  border-radius: 0.5rem;
}
.value {
  font-size: 1.5rem;
  font-weight: 600;
}
.label {
  color: var(--p-text-muted-color);
}
.spread {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  margin-top: 1.5rem;
}
</style>
