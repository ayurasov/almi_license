<script setup lang="ts">
// Journal (E10-04): audit events by object, user, type and period, newest first, and the CSV
// of the same filter. A customer viewer gets the events of its licences only (the server filters).
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable, { type DataTablePageEvent } from 'primevue/datatable'
import DatePicker from 'primevue/datepicker'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { type AuditEvent, EMPTY_FILTER, PAGE_SIZE, useAuditStore } from '@/stores/audit'

const { t, d } = useI18n()
const store = useAuditStore()
const filter = reactive({ ...EMPTY_FILTER })
const page = ref(1)
const exporting = ref(false)
const objectTypes = computed(() =>
  ['', 'license', 'activation', 'customer', 'user', 'local_server', 'product', 'profile', 'import', 'article'].map((value) => ({
    value,
    label: value ? t(`audit.objects.${value}`) : t('audit.all'),
  })),
)

onMounted(() => void store.load(filter))

function search(): void {
  page.value = 1
  void store.load(filter)
}

function onPage(event: DataTablePageEvent): void {
  page.value = event.page + 1
  void store.load(filter, page.value)
}

function details(event: AuditEvent): string {
  return Object.keys(event.data).length ? JSON.stringify(event.data) : ''
}

async function exportCsv(): Promise<void> {
  exporting.value = true
  try {
    const blob = await store.exportCsv(filter)
    const url = URL.createObjectURL(blob)
    const link = Object.assign(document.createElement('a'), { href: url, download: 'almi-audit.csv' })
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
      <h1>{{ t('audit.title') }}</h1>
      <Button
        :label="t('audit.export')"
        icon="pi pi-download"
        :loading="exporting"
        data-testid="audit-export"
        @click="exportCsv"
      />
    </div>
    <div class="panel">
      <form
        class="filters"
        @submit.prevent="search"
      >
        <Select
          v-model="filter.objectType"
          :options="objectTypes"
          option-label="label"
          option-value="value"
          :aria-label="t('audit.object')"
          data-testid="audit-object-type"
        />
        <InputText
          v-model="filter.objectId"
          :placeholder="t('audit.objectId')"
          :aria-label="t('audit.objectId')"
        />
        <InputText
          v-model="filter.actor"
          :placeholder="t('audit.actor')"
          :aria-label="t('audit.actor')"
          data-testid="audit-actor"
        />
        <InputText
          v-model="filter.action"
          :placeholder="t('audit.action')"
          :aria-label="t('audit.action')"
          data-testid="audit-action"
        />
        <DatePicker
          v-model="filter.since"
          :placeholder="t('audit.since')"
          :aria-label="t('audit.since')"
          show-time
        />
        <DatePicker
          v-model="filter.until"
          :placeholder="t('audit.until')"
          :aria-label="t('audit.until')"
          show-time
        />
        <Button
          type="submit"
          :label="t('audit.search')"
          icon="pi pi-search"
          data-testid="audit-search"
        />
      </form>
      <Message
        v-if="store.failed === 'network'"
        severity="error"
      >
        {{ t('errors.network') }}
      </Message>
      <DataTable
        :value="store.items"
        :loading="store.loading"
        lazy
        paginator
        :rows="PAGE_SIZE"
        :total-records="store.count"
        :first="(page - 1) * PAGE_SIZE"
        data-key="seq"
        data-testid="audit-table"
        @page="onPage"
      >
        <template #empty>
          {{ t('audit.empty') }}
        </template>
        <Column :header="t('audit.columns.at')">
          <template #body="{ data }">
            {{ d(new Date((data as AuditEvent).at), 'long') }}
          </template>
        </Column>
        <Column
          field="actor"
          :header="t('audit.columns.actor')"
        />
        <Column
          field="action"
          :header="t('audit.columns.action')"
        />
        <Column :header="t('audit.columns.object')">
          <template #body="{ data }">
            {{ (data as AuditEvent).object_type }} <code>{{ (data as AuditEvent).object_id }}</code>
          </template>
        </Column>
        <Column :header="t('audit.columns.details')">
          <template #body="{ data }">
            <code class="details">{{ details(data as AuditEvent) }}</code>
          </template>
        </Column>
      </DataTable>
    </div>
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
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.details {
  font-size: 0.8rem;
  word-break: break-all;
}
</style>
