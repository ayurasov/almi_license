<script setup lang="ts">
// Reference screen (console/docs/reference-screen.md): lazy DataTable, filters in the URL query,
// dialog form, empty / loading / network error states.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable, { type DataTablePageEvent, type DataTableSortEvent } from 'primevue/datatable'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { type LocationQuery, useRoute, useRouter } from 'vue-router'

import CustomerDialog from '@/components/CustomerDialog.vue'
import { type Customer, type CustomerQuery, DEFAULT_QUERY, useCustomersStore } from '@/stores/customers'

const { t, d } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useCustomersStore()
const dialogOpen = ref(false)
const editing = ref<Customer | null>(null)

function text(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback
}

function number(value: unknown, fallback: number): number {
  const parsed = Number(text(value, ''))
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

function fromUrl(query: LocationQuery): CustomerQuery {
  return {
    page: number(query.page, DEFAULT_QUERY.page),
    pageSize: number(query.page_size, DEFAULT_QUERY.pageSize),
    ordering: text(query.ordering, DEFAULT_QUERY.ordering),
    name: text(query.name, ''),
    inn: text(query.inn, ''),
    status: text(query.status, ''),
  }
}

const query = computed(() => fromUrl(route.query))
const filters = ref({ name: query.value.name, inn: query.value.inn, status: query.value.status })
const statuses = computed(() => [
  { value: '', label: t('customers.filters.any') },
  { value: 'active', label: t('customers.status.active') },
  { value: 'archived', label: t('customers.status.archived') },
])

function navigate(change: Partial<CustomerQuery>): void {
  const next = { ...query.value, ...change }
  void router.replace({
    query: {
      page: String(next.page),
      page_size: String(next.pageSize),
      ordering: next.ordering,
      ...(next.name ? { name: next.name } : {}),
      ...(next.inn ? { inn: next.inn } : {}),
      ...(next.status ? { status: next.status } : {}),
    },
  })
}

watch(query, (value) => void store.list(value), { immediate: true })

function applyFilters(): void {
  navigate({ ...filters.value, page: 1 })
}

const filtered = computed(() => Boolean(query.value.name || query.value.inn || query.value.status))

function resetFilters(): void {
  filters.value = { name: '', inn: '', status: '' }
  navigate({ name: '', inn: '', status: '', page: 1 })
}

function onPage(event: DataTablePageEvent): void {
  navigate({ page: event.page + 1, pageSize: event.rows })
}

function onSort(event: DataTableSortEvent): void {
  const field = typeof event.sortField === 'string' ? event.sortField : 'name'
  navigate({ ordering: event.sortOrder === -1 ? `-${field}` : field, page: 1 })
}

const sortField = computed(() => query.value.ordering.replace(/^-/, ''))
const sortOrder = computed(() => (query.value.ordering.startsWith('-') ? -1 : 1))

function openCreate(): void {
  editing.value = null
  dialogOpen.value = true
}

function openEdit(customer: Customer): void {
  editing.value = customer
  dialogOpen.value = true
}
</script>

<template>
  <section>
    <div class="toolbar">
      <h1>{{ t('customers.title') }}</h1>
      <Button
        :label="t('customers.create')"
        icon="pi pi-plus"
        data-testid="customer-create"
        @click="openCreate"
      />
    </div>

    <div class="panel">
      <form
        class="filters"
        @submit.prevent="applyFilters"
      >
        <InputText
          v-model="filters.name"
          :placeholder="t('customers.filters.name')"
          data-testid="filter-name"
        />
        <InputText
          v-model="filters.inn"
          :placeholder="t('customers.filters.inn')"
          data-testid="filter-inn"
        />
        <Select
          v-model="filters.status"
          :options="statuses"
          option-label="label"
          option-value="value"
          :placeholder="t('customers.filters.status')"
        />
        <Button
          type="submit"
          icon="pi pi-search"
          :label="t('common.find')"
          :aria-label="t('customers.filters.name')"
          data-testid="filter-apply"
        />
        <Button
          v-if="filtered"
          :label="t('common.reset')"
          icon="pi pi-filter-slash"
          text
          severity="secondary"
          data-testid="filter-reset"
          @click="resetFilters"
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
        data-testid="customers-table"
        @page="onPage"
        @sort="onSort"
      >
        <template #empty>
          {{ t('customers.empty') }}
        </template>
        <Column
          field="name"
          :header="t('customers.columns.name')"
          sortable
        />
        <Column
          field="inn"
          :header="t('customers.columns.inn')"
          sortable
        />
        <Column
          field="external_id"
          :header="t('customers.columns.externalId')"
        />
        <Column
          field="status"
          :header="t('customers.columns.status')"
        >
          <template #body="{ data }">
            <Tag
              :value="t(`customers.status.${(data as Customer).status}`)"
              :severity="(data as Customer).status === 'active' ? 'success' : 'secondary'"
            />
          </template>
        </Column>
        <Column
          field="created_at"
          :header="t('customers.columns.createdAt')"
          sortable
        >
          <template #body="{ data }">
            {{ d(new Date((data as Customer).created_at)) }}
          </template>
        </Column>
        <Column>
          <template #body="{ data }">
            <Button
              icon="pi pi-pencil"
              text
              :aria-label="t('customers.edit')"
              @click="openEdit(data as Customer)"
            />
          </template>
        </Column>
      </DataTable>
    </div>

    <CustomerDialog
      v-model:visible="dialogOpen"
      :customer="editing"
      @saved="store.list(query)"
    />
  </section>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filters {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
</style>
