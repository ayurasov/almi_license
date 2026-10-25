<script setup lang="ts">
// Local servers of customers (E09-02): seats handed over by license, a one-time registration
// code, registration by file for closed networks.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '@/api/client'
import type { components } from '@/api/generated/admin'
import { ApiError } from '@/api/problem'
import { download, type LocalServer, useServersStore } from '@/stores/servers'

type Customer = components['schemas']['Customer']
type License = components['schemas']['License']

const { t, d } = useI18n()
const toast = useToast()
const store = useServersStore()
const createOpen = ref(false)
const customers = ref<Customer[]>([])
const licenses = ref<License[]>([])
const productCodes = ref<Record<string, string>>({})
const draft = reactive<{ customerId: string; name: string; seats: Record<string, number> }>({
  customerId: '',
  name: '',
  seats: {},
})
const errors = ref<string[]>([])
const issued = ref<string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

onMounted(() => {
  void store.list()
})

async function run(action: () => Promise<unknown>): Promise<boolean> {
  errors.value = []
  try {
    await action()
    return true
  } catch (failure) {
    if (failure instanceof ApiError) {
      errors.value = failure.hasFieldErrors ? Object.values(failure.fieldErrors).flat() : [failure.message]
    } else errors.value = [t('errors.network')]
    return false
  }
}

async function openCreate(): Promise<void> {
  Object.assign(draft, { customerId: '', name: '', seats: {} })
  licenses.value = []
  createOpen.value = true
  const { data } = await api.GET('/api/admin/customers', { params: { query: { page_size: 100, status: 'active' } } })
  customers.value = data?.results ?? []
  const products = await api.GET('/api/admin/products')
  productCodes.value = Object.fromEntries((products.data ?? []).map((product) => [product.id, product.code]))
}

async function pickCustomer(id: string): Promise<void> {
  draft.customerId = id
  draft.seats = {}
  const { data } = await api.GET('/api/admin/licenses', {
    params: { query: { customer_id: id, status: 'active', page_size: 100 } },
  })
  licenses.value = data?.results ?? []
}

async function create(): Promise<void> {
  const seats = Object.fromEntries(Object.entries(draft.seats).filter(([, value]) => value > 0))
  await run(async () => {
    const result = await store.create(draft.customerId, draft.name, seats)
    createOpen.value = false
    issued.value = result.code
  })
}

async function newCode(server: LocalServer): Promise<void> {
  await run(async () => {
    issued.value = (await store.newCode(server.id)).code
  })
}

async function registerFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await run(async () => {
    const document = await store.registerFile(file)
    download(file.name.replace(/\.alk-req$/, '') + '.alk', document)
    toast.add({ severity: 'success', summary: t('servers.registered'), life: 3000 })
  })
  if (fileInput.value) fileInput.value.value = ''
}

function seats(server: LocalServer): number {
  return Object.values(server.allocations).reduce((total, value) => total + value, 0)
}
</script>

<template>
  <section>
    <div class="toolbar">
      <h1>{{ t('servers.title') }}</h1>
      <div class="actions">
        <label
          class="p-button p-button-secondary"
          for="register-file"
        >{{ t('servers.registerFile') }}</label>
        <input
          id="register-file"
          ref="fileInput"
          class="hidden"
          type="file"
          accept=".alk-req,application/json"
          data-testid="register-file"
          @change="registerFile"
        >
        <Button
          :label="t('servers.create')"
          icon="pi pi-plus"
          data-testid="server-create"
          @click="openCreate"
        />
      </div>
    </div>
    <p class="hint">
      {{ t('servers.registerHint') }}
    </p>
    <Message
      v-for="text in errors"
      :key="text"
      severity="error"
      data-testid="server-error"
    >
      {{ text }}
    </Message>
    <Message
      v-if="store.failed === 'network'"
      severity="error"
    >
      {{ t('errors.network') }}
    </Message>

    <DataTable
      :value="store.items"
      :loading="store.loading"
      data-key="id"
      data-testid="servers-table"
    >
      <template #empty>
        {{ t('servers.empty') }}
      </template>
      <Column
        field="name"
        :header="t('servers.columns.name')"
      />
      <Column :header="t('servers.columns.serverId')">
        <template #body="{ data }">
          <code v-if="(data as LocalServer).registered">{{ (data as LocalServer).server_id }}</code>
        </template>
      </Column>
      <Column :header="t('servers.columns.status')">
        <template #body="{ data }">
          <Tag
            :value="t(`servers.status.${(data as LocalServer).status}`)"
            :severity="(data as LocalServer).status === 'active' ? 'success' : 'secondary'"
          />
        </template>
      </Column>
      <Column :header="t('servers.columns.seats')">
        <template #body="{ data }">
          {{ seats(data as LocalServer) }}
        </template>
      </Column>
      <Column :header="t('servers.columns.package')">
        <template #body="{ data }">
          {{ (data as LocalServer).last_package_seq || '—' }}
          <Tag
            v-if="(data as LocalServer).package_expires_soon"
            :value="t('servers.packageExpires', { date: d(new Date((data as LocalServer).package_valid_until ?? '')) })"
            severity="warn"
            data-testid="package-expires"
          />
        </template>
      </Column>
      <Column :header="t('servers.columns.lastSeen')">
        <template #body="{ data }">
          {{ (data as LocalServer).last_seen_at ? d(new Date((data as LocalServer).last_seen_at ?? '')) : t('servers.never') }}
        </template>
      </Column>
      <Column>
        <template #body="{ data }">
          <Button
            v-if="!(data as LocalServer).registered"
            text
            size="small"
            :label="t('servers.newCode')"
            @click="newCode(data as LocalServer)"
          />
        </template>
      </Column>
    </DataTable>

    <Dialog
      v-model:visible="createOpen"
      modal
      :header="t('servers.create')"
      :style="{ width: '34rem' }"
    >
      <form
        class="form"
        @submit.prevent="create"
      >
        <label for="server-customer">{{ t('servers.form.customer') }}</label>
        <Select
          :model-value="draft.customerId"
          input-id="server-customer"
          :options="customers"
          option-label="name"
          option-value="id"
          filter
          data-testid="server-customer"
          @update:model-value="pickCustomer($event as string)"
        />
        <label for="server-name">{{ t('servers.form.name') }}</label>
        <InputText
          id="server-name"
          v-model="draft.name"
          data-testid="server-name"
        />
        <p
          v-if="draft.customerId && licenses.length === 0"
          class="hint"
        >
          {{ t('servers.noLicenses') }}
        </p>
        <div
          v-for="license in licenses"
          :key="license.id"
          class="seat"
        >
          <span>{{ productCodes[license.product_id] ?? license.product_id }} · {{ license.limit }}</span>
          <InputNumber
            v-model="draft.seats[license.id]"
            :min="0"
            :max="license.limit"
            :placeholder="t('servers.form.seats')"
            data-testid="server-seats"
          />
        </div>
        <div class="actions end">
          <Button
            :label="t('servers.form.cancel')"
            severity="secondary"
            text
            @click="createOpen = false"
          />
          <Button
            type="submit"
            :label="t('servers.form.save')"
            data-testid="server-save"
          />
        </div>
      </form>
    </Dialog>

    <Dialog
      :visible="issued !== null"
      modal
      :closable="false"
      :header="t('servers.code.title')"
      :style="{ width: '28rem' }"
    >
      <Message severity="warn">
        {{ t('servers.code.once') }}
      </Message>
      <p class="code">
        <code data-testid="registration-code">{{ issued }}</code>
      </p>
      <Button
        :label="t('servers.code.close')"
        data-testid="registration-code-close"
        @click="issued = null"
      />
    </Dialog>
  </section>
</template>

<style scoped>
.toolbar,
.actions,
.seat {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.toolbar {
  justify-content: space-between;
}
.end {
  justify-content: flex-end;
  margin-top: 1rem;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.seat span {
  min-width: 14rem;
}
.hidden {
  display: none;
}
.hint {
  color: var(--p-text-muted-color);
}
.code code {
  font-size: 1.25rem;
  user-select: all;
}
</style>
