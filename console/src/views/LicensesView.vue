<script setup lang="ts">
// Licenses (E07-04), built like CustomersView (docs/reference-screen.md): lazy table, filters in the URL.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable, { type DataTablePageEvent, type DataTableSortEvent } from 'primevue/datatable'
import DatePicker from 'primevue/datepicker'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { type LocationQuery, useRoute, useRouter } from 'vue-router'

import { DEFAULT_QUERY, useCustomersStore } from '@/stores/customers'
import { DEFAULT_LICENSE_QUERY, type License, type LicenseQuery, useLicensesStore } from '@/stores/licenses'

const { t, d } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useLicensesStore()
const customers = useCustomersStore()

function text(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback
}

function number(value: unknown, fallback: number): number {
  const parsed = Number(text(value, ''))
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

function fromUrl(query: LocationQuery): LicenseQuery {
  return {
    page: number(query.page, DEFAULT_LICENSE_QUERY.page),
    pageSize: number(query.page_size, DEFAULT_LICENSE_QUERY.pageSize),
    ordering: text(query.ordering, DEFAULT_LICENSE_QUERY.ordering),
    productId: text(query.product_id, ''),
    customerId: text(query.customer_id, ''),
    status: text(query.status, ''),
    expiresBefore: text(query.expires_before, ''),
  }
}

const query = computed(() => fromUrl(route.query))
const filters = ref({
  productId: query.value.productId,
  customerId: query.value.customerId,
  status: query.value.status,
  expiresBefore: query.value.expiresBefore ? new Date(query.value.expiresBefore) : null,
})

const productOptions = computed(() => [
  { value: '', label: t('licenses.filters.any') },
  ...store.products.map((product) => ({ value: product.id, label: product.name.ru ?? product.code })),
])
const customerOptions = computed(() => [
  { value: '', label: t('licenses.filters.any') },
  ...customers.items.map((customer) => ({ value: customer.id, label: customer.name })),
])
const statusOptions = computed(() => [
  { value: '', label: t('licenses.filters.any') },
  ...(['active', 'suspended', 'revoked'] as const).map((value) => ({ value, label: t(`licenses.status.${value}`) })),
])

function productName(id: string): string {
  const product = store.products.find((item) => item.id === id)
  return product ? (product.name.ru ?? product.code) : id
}

function navigate(change: Partial<LicenseQuery>): void {
  const next = { ...query.value, ...change }
  void router.replace({
    query: {
      page: String(next.page),
      page_size: String(next.pageSize),
      ordering: next.ordering,
      ...(next.productId ? { product_id: next.productId } : {}),
      ...(next.customerId ? { customer_id: next.customerId } : {}),
      ...(next.status ? { status: next.status } : {}),
      ...(next.expiresBefore ? { expires_before: next.expiresBefore } : {}),
    },
  })
}

onMounted(() => {
  void store.loadProducts()
  void customers.list({ ...DEFAULT_QUERY, pageSize: 100 })
})
watch(query, (value) => void store.list(value), { immediate: true })

function applyFilters(): void {
  const { expiresBefore, ...rest } = filters.value
  navigate({ ...rest, expiresBefore: expiresBefore ? expiresBefore.toISOString() : '', page: 1 })
}

function onPage(event: DataTablePageEvent): void {
  navigate({ page: event.page + 1, pageSize: event.rows })
}

function onSort(event: DataTableSortEvent): void {
  const field = typeof event.sortField === 'string' ? event.sortField : 'valid_until'
  navigate({ ordering: event.sortOrder === -1 ? `-${field}` : field, page: 1 })
}

const sortField = computed(() => query.value.ordering.replace(/^-/, ''))
const sortOrder = computed(() => (query.value.ordering.startsWith('-') ? -1 : 1))

function open(license: License): void {
  void router.push({ name: 'license', params: { id: license.id } })
}
</script>

<template>
  <section>
    <h1>{{ t('licenses.title') }}</h1>

    <form
      class="filters"
      @submit.prevent="applyFilters"
    >
      <Select
        v-model="filters.productId"
        :options="productOptions"
        option-label="label"
        option-value="value"
        :placeholder="t('licenses.filters.product')"
      />
      <Select
        v-model="filters.customerId"
        :options="customerOptions"
        option-label="label"
        option-value="value"
        filter
        :placeholder="t('licenses.filters.customer')"
      />
      <Select
        v-model="filters.status"
        :options="statusOptions"
        option-label="label"
        option-value="value"
        :placeholder="t('licenses.filters.status')"
        data-testid="filter-status"
      />
      <DatePicker
        v-model="filters.expiresBefore"
        :placeholder="t('licenses.filters.expiresBefore')"
        show-button-bar
      />
      <Button
        type="submit"
        icon="pi pi-search"
        :aria-label="t('licenses.filters.status')"
        data-testid="filter-apply"
      />
    </form>

    <Message
      v-if="store.failed === 'network'"
      severity="error"
    >
      {{ t('errors.network') }}
      <Button
        :label="t('errors.retry')"
        text
        @click="store.list(query)"
      />
    </Message>

    <DataTable
      :value="store.items"
      lazy
      paginator
      data-key="id"
      :loading="store.loading"
      :rows="query.pageSize"
      :first="(query.page - 1) * query.pageSize"
      :total-records="store.total"
      :rows-per-page-options="[10, 20, 50, 100]"
      :sort-field="sortField"
      :sort-order="sortOrder"
      data-testid="licenses-table"
      @page="onPage"
      @sort="onSort"
    >
      <template #empty>
        {{ t('licenses.empty') }}
      </template>
      <Column
        field="customer_name"
        :header="t('licenses.columns.customer')"
      />
      <Column :header="t('licenses.columns.product')">
        <template #body="{ data }">
          {{ productName((data as License).product_id) }}
        </template>
      </Column>
      <Column :header="t('licenses.columns.type')">
        <template #body="{ data }">
          {{ t(`licenses.type.${(data as License).type}`) }}
        </template>
      </Column>
      <Column
        field="status"
        :header="t('licenses.columns.status')"
        sortable
      >
        <template #body="{ data }">
          <Tag
            :value="t(`licenses.status.${(data as License).status}`)"
            :severity="(data as License).status === 'active' ? 'success' : 'warn'"
          />
        </template>
      </Column>
      <Column
        field="limit"
        :header="t('licenses.columns.limit')"
      />
      <Column
        field="valid_until"
        :header="t('licenses.columns.validUntil')"
        sortable
      >
        <template #body="{ data }">
          {{ (data as License).valid_until ? d(new Date((data as License).valid_until ?? '')) : t('licenses.perpetual') }}
        </template>
      </Column>
      <Column :header="t('licenses.columns.enforcement')">
        <template #body="{ data }">
          {{ t(`licenses.enforcement.${(data as License).enforcement || 'profile'}`) }}
        </template>
      </Column>
      <Column>
        <template #body="{ data }">
          <Button
            icon="pi pi-arrow-right"
            text
            :aria-label="t('licenses.open')"
            data-testid="license-open"
            @click="open(data as License)"
          />
        </template>
      </Column>
    </DataTable>
  </section>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
</style>
