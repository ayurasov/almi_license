<script setup lang="ts">
// Activations (E07-05), built like CustomersView (docs/reference-screen.md): search by activation id,
// name or version; reserve and conflict marks; manual release with a reason.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable, { type DataTablePageEvent, type DataTableSortEvent } from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { type LocationQuery, useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/problem'
import DirectiveDialog from '@/components/DirectiveDialog.vue'
import {
  type Activation,
  type ActivationQuery,
  DEFAULT_ACTIVATION_QUERY,
  useActivationsStore,
} from '@/stores/activations'

const { t, d } = useI18n()
const toast = useToast()
const route = useRoute()
const router = useRouter()
const store = useActivationsStore()
const releasing = ref<Activation | null>(null)
const reason = ref('')
const releaseErrors = ref<string[]>([])
const directiveTarget = ref<{ kind: 'activation'; id: string } | null>(null)

function text(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback
}

function number(value: unknown, fallback: number): number {
  const parsed = Number(text(value, ''))
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback
}

function fromUrl(query: LocationQuery): ActivationQuery {
  return {
    page: number(query.page, DEFAULT_ACTIVATION_QUERY.page),
    pageSize: number(query.page_size, DEFAULT_ACTIVATION_QUERY.pageSize),
    ordering: text(query.ordering, DEFAULT_ACTIVATION_QUERY.ordering),
    licenseId: text(query.license_id, ''),
    search: text(query.search, ''),
    status: text(query.status, ''),
  }
}

const query = computed(() => fromUrl(route.query))
const filters = ref({ search: query.value.search, status: query.value.status })
const statusOptions = computed(() => [
  { value: '', label: t('activations.filters.any') },
  ...(['active', 'released', 'released_auto', 'revoked', 'conflict'] as const).map((value) => ({
    value,
    label: t(`activations.status.${value}`),
  })),
])

function navigate(change: Partial<ActivationQuery>): void {
  const next = { ...query.value, ...change }
  void router.replace({
    query: {
      page: String(next.page),
      page_size: String(next.pageSize),
      ordering: next.ordering,
      ...(next.licenseId ? { license_id: next.licenseId } : {}),
      ...(next.search ? { search: next.search } : {}),
      ...(next.status ? { status: next.status } : {}),
    },
  })
}

watch(query, (value) => void store.list(value), { immediate: true })

function applyFilters(): void {
  navigate({ ...filters.value, page: 1 })
}

function onPage(event: DataTablePageEvent): void {
  navigate({ page: event.page + 1, pageSize: event.rows })
}

function onSort(event: DataTableSortEvent): void {
  const field = typeof event.sortField === 'string' ? event.sortField : 'last_seen_at'
  navigate({ ordering: event.sortOrder === -1 ? `-${field}` : field, page: 1 })
}

const sortField = computed(() => query.value.ordering.replace(/^-/, ''))
const sortOrder = computed(() => (query.value.ordering.startsWith('-') ? -1 : 1))

function startRelease(activation: Activation): void {
  releasing.value = activation
  reason.value = ''
  releaseErrors.value = []
}

async function release(): Promise<void> {
  if (!releasing.value) return
  try {
    await store.release(releasing.value.activation_id, reason.value)
    toast.add({ severity: 'success', summary: t('activations.released'), life: 3000 })
    releasing.value = null
    await store.list(query.value)
  } catch (failure) {
    releaseErrors.value =
      failure instanceof ApiError ? Object.values(failure.fieldErrors).flat() : [t('errors.network')]
  }
}
</script>

<template>
  <section>
    <h1>{{ t('activations.title') }}</h1>

    <form
      class="filters"
      @submit.prevent="applyFilters"
    >
      <InputText
        v-model="filters.search"
        :placeholder="t('activations.filters.search')"
        data-testid="filter-search"
      />
      <Select
        v-model="filters.status"
        :options="statusOptions"
        option-label="label"
        option-value="value"
        :placeholder="t('activations.filters.status')"
      />
      <Button
        type="submit"
        icon="pi pi-search"
        :aria-label="t('activations.filters.search')"
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
      data-key="activation_id"
      :loading="store.loading"
      :rows="query.pageSize"
      :first="(query.page - 1) * query.pageSize"
      :total-records="store.total"
      :rows-per-page-options="[10, 20, 50, 100]"
      :sort-field="sortField"
      :sort-order="sortOrder"
      data-testid="activations-table"
      @page="onPage"
      @sort="onSort"
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
      <Column :header="t('activations.columns.marks')">
        <template #body="{ data }">
          <Tag
            v-if="(data as Activation).in_reserve"
            :value="t('activations.reserve')"
            severity="warn"
          />
          <Tag
            v-if="(data as Activation).offline"
            :value="t('activations.offline')"
            severity="info"
            data-testid="activation-offline"
          />
          <Tag
            v-if="(data as Activation).status === 'conflict'"
            :value="t('activations.conflict')"
            severity="danger"
          />
        </template>
      </Column>
      <Column
        field="last_seen_at"
        :header="t('activations.columns.lastSeen')"
        sortable
      >
        <template #body="{ data }">
          {{ d(new Date((data as Activation).last_seen_at)) }}
        </template>
      </Column>
      <Column>
        <template #body="{ data }">
          <Button
            v-if="(data as Activation).status === 'active'"
            :label="t('activations.release')"
            text
            data-testid="activation-release"
            @click="startRelease(data as Activation)"
          />
          <Button
            v-if="(data as Activation).status === 'active'"
            :label="t('activations.directive')"
            text
            data-testid="activation-directive"
            @click="directiveTarget = { kind: 'activation', id: (data as Activation).activation_id }"
          />
        </template>
      </Column>
    </DataTable>

    <DirectiveDialog
      :target="directiveTarget"
      @close="directiveTarget = null"
      @sent="directiveTarget = null"
    />
    <Dialog
      :visible="releasing !== null"
      modal
      :header="t('activations.releaseTitle')"
      :style="{ width: '30rem' }"
      @update:visible="releasing = null"
    >
      <form
        class="release-form"
        @submit.prevent="release"
      >
        <Message severity="info">
          {{ t('activations.releaseHint') }}
        </Message>
        <label for="release-reason">{{ t('activations.reason') }}</label>
        <Textarea
          id="release-reason"
          v-model="reason"
          rows="3"
          :invalid="releaseErrors.length > 0"
        />
        <small
          v-for="message in releaseErrors"
          :key="message"
          class="p-error"
        >{{ message }}</small>
        <div class="release-buttons">
          <Button
            type="button"
            :label="t('activations.cancel')"
            severity="secondary"
            @click="releasing = null"
          />
          <Button
            type="submit"
            :label="t('activations.confirm')"
            severity="danger"
            data-testid="release-confirm"
          />
        </div>
      </form>
    </Dialog>
  </section>
</template>

<style scoped>
.filters {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.release-form {
  display: grid;
  gap: 0.4rem;
}
.release-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
