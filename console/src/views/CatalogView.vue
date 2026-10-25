<script setup lang="ts">
// Catalog (E07-06, E01-02): products on the left, the chosen product with its capabilities and
// editions on the right. Products are archived, never deleted (licenses refer to them).
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/problem'
import { type ProductDetails, type ProductSummary, useCatalogStore } from '@/stores/catalog'

const { t } = useI18n()
const toast = useToast()
const store = useCatalogStore()
const errors = ref<Record<string, string[]>>({})
const createOpen = ref(false)
const draft = reactive<{ code: string; name: string; subject_type: ProductDetails['subject_type']; default_metric_id: string }>({
  code: '',
  name: '',
  subject_type: 'device',
  default_metric_id: '',
})
const settings = reactive<{ status: ProductDetails['status']; default_profile_code: string }>({
  status: 'active',
  default_profile_code: '',
})
const capability = reactive({ code: '', name: '' })
const edition = reactive({ code: '', name: '' })
const editionCaps = ref<Record<string, string[]>>({})

const statuses = computed(() =>
  (['active', 'reserved', 'deprecated'] as const).map((value) => ({ value, label: t(`catalog.status.${value}`) })),
)
const subjects = computed(() =>
  (['device', 'server_instance', 'os_node'] as const).map((value) => ({ value, label: t(`catalog.subject.${value}`) })),
)
const capabilityCodes = computed(() => store.current?.capabilities.map((item) => item.code) ?? [])

onMounted(() => void store.load())

watch(
  () => store.current,
  (product) => {
    if (!product) return
    settings.status = product.status
    settings.default_profile_code = product.default_profile_code
    editionCaps.value = Object.fromEntries(product.editions.map((e) => [e.code, [...(e.base_capabilities ?? [])]]))
  },
)

// Every change returns the whole product; field errors of the server are shown next to the form.
async function run(action: () => Promise<unknown>): Promise<boolean> {
  errors.value = {}
  try {
    await action()
    toast.add({ severity: 'success', summary: t('catalog.saved'), life: 3000 })
    return true
  } catch (failure) {
    if (failure instanceof ApiError && failure.hasFieldErrors) errors.value = failure.fieldErrors
    else if (!(failure instanceof ApiError)) errors.value = { form: [t('errors.network')] }
    return false
  }
}

function select(row: ProductSummary): void {
  errors.value = {}
  void store.open(row.id)
}

async function createProduct(): Promise<void> {
  const done = await run(() =>
    store.createProduct({
      code: draft.code,
      name: { ru: draft.name },
      subject_type: draft.subject_type,
      default_metric_id: draft.default_metric_id,
      default_profile_code: '',
    }),
  )
  if (done) createOpen.value = false
}

async function saveSettings(product: ProductDetails): Promise<void> {
  await run(() => store.updateProduct(product.id, { ...settings }))
  await store.load()
}

async function addCapability(product: ProductDetails): Promise<void> {
  const name: Record<string, string> = capability.name ? { ru: capability.name } : {}
  if (await run(() => store.addCapability(product.id, capability.code, name))) Object.assign(capability, { code: '', name: '' })
}

function toggleCapability(product: ProductDetails, code: string, status: string | undefined): void {
  void run(() => store.setCapabilityStatus(product.id, code, status === 'deprecated' ? 'active' : 'deprecated'))
}

function saveEditionCaps(product: ProductDetails, code: string, name: Record<string, string> | undefined): void {
  void run(() => store.saveEdition(product.id, code, name ?? {}, editionCaps.value[code] ?? []))
}

async function addEdition(product: ProductDetails): Promise<void> {
  const name: Record<string, string> = edition.name ? { ru: edition.name } : {}
  if (await run(() => store.saveEdition(product.id, edition.code, name, []))) Object.assign(edition, { code: '', name: '' })
}
</script>

<template>
  <section>
    <div class="toolbar">
      <h1>{{ t('catalog.title') }}</h1>
      <Button
        :label="t('catalog.create')"
        icon="pi pi-plus"
        data-testid="product-create"
        @click="createOpen = true"
      />
    </div>

    <Message
      v-if="store.failed === 'network'"
      severity="error"
    >
      {{ t('errors.network') }}
      <Button
        :label="t('errors.retry')"
        text
        @click="store.load()"
      />
    </Message>
    <Message
      v-for="text in errors.form ?? []"
      :key="text"
      severity="error"
    >
      {{ text }}
    </Message>

    <div class="split">
      <DataTable
        :value="store.products"
        :loading="store.loading"
        data-key="id"
        selection-mode="single"
        :selection="store.products.find((p) => p.id === store.current?.id)"
        data-testid="products-table"
        @row-select="select($event.data as ProductSummary)"
      >
        <template #empty>
          {{ t('catalog.empty') }}
        </template>
        <Column
          field="code"
          :header="t('catalog.columns.code')"
        />
        <Column :header="t('catalog.columns.name')">
          <template #body="{ data }">
            {{ (data as ProductSummary).name.ru }}
          </template>
        </Column>
        <Column
          field="default_metric"
          :header="t('catalog.columns.metric')"
        />
      </DataTable>

      <div
        v-if="store.current"
        class="details"
        data-testid="product-details"
      >
        <h2>{{ store.current.name.ru }} <small>{{ store.current.code }}</small></h2>
        <form
          class="row"
          @submit.prevent="saveSettings(store.current)"
        >
          <Select
            v-model="settings.status"
            :options="statuses"
            option-label="label"
            option-value="value"
            :aria-label="t('catalog.form.status')"
            data-testid="product-status"
          />
          <InputText
            v-model="settings.default_profile_code"
            :placeholder="t('catalog.form.profile')"
            :invalid="!!errors.default_profile_code"
          />
          <Button
            type="submit"
            :label="t('catalog.form.save')"
            data-testid="product-save"
          />
        </form>
        <small
          v-for="text in errors.default_profile_code ?? []"
          :key="text"
          class="error"
        >{{ text }}</small>

        <h3>{{ t('catalog.capabilities.title') }}</h3>
        <p class="hint">
          {{ t('catalog.capabilities.hint') }}
        </p>
        <DataTable
          :value="store.current.capabilities"
          data-key="code"
          size="small"
          data-testid="capabilities-table"
        >
          <Column
            field="code"
            :header="t('catalog.columns.code')"
          />
          <Column :header="t('catalog.columns.name')">
            <template #body="{ data }">
              {{ data.name?.ru ?? '' }}
            </template>
          </Column>
          <Column :header="t('catalog.columns.status')">
            <template #body="{ data }">
              <Tag
                :value="t(`catalog.status.${data.status ?? 'active'}`)"
                :severity="data.status === 'deprecated' ? 'secondary' : 'success'"
              />
            </template>
          </Column>
          <Column>
            <template #body="{ data }">
              <Button
                text
                size="small"
                :label="data.status === 'deprecated' ? t('catalog.capabilities.restore') : t('catalog.capabilities.deprecate')"
                @click="toggleCapability(store.current, data.code, data.status)"
              />
            </template>
          </Column>
        </DataTable>
        <form
          class="row"
          @submit.prevent="addCapability(store.current)"
        >
          <InputText
            v-model="capability.code"
            :placeholder="t('catalog.form.code')"
            :invalid="!!errors.code"
            data-testid="capability-code"
          />
          <InputText
            v-model="capability.name"
            :placeholder="t('catalog.form.name')"
          />
          <Button
            type="submit"
            icon="pi pi-plus"
            :label="t('catalog.capabilities.add')"
            data-testid="capability-add"
          />
        </form>
        <small
          v-for="text in errors.code ?? []"
          :key="text"
          class="error"
        >{{ text }}</small>

        <h3>{{ t('catalog.editions.title') }}</h3>
        <div
          v-for="item in store.current.editions"
          :key="item.code"
          class="row"
        >
          <strong class="edition">{{ item.code }}</strong>
          <MultiSelect
            v-model="editionCaps[item.code]"
            :options="capabilityCodes"
            :placeholder="t('catalog.editions.base')"
            display="chip"
            :data-testid="`edition-${item.code}`"
          />
          <Button
            :label="t('catalog.editions.save')"
            text
            @click="saveEditionCaps(store.current, item.code, item.name)"
          />
        </div>
        <small
          v-for="text in errors.base_capabilities ?? []"
          :key="text"
          class="error"
        >{{ text }}</small>
        <form
          class="row"
          @submit.prevent="addEdition(store.current)"
        >
          <InputText
            v-model="edition.code"
            :placeholder="t('catalog.form.code')"
          />
          <InputText
            v-model="edition.name"
            :placeholder="t('catalog.form.name')"
          />
          <Button
            type="submit"
            icon="pi pi-plus"
            :label="t('catalog.editions.add')"
          />
        </form>
      </div>
      <p
        v-else
        class="hint"
      >
        {{ t('catalog.choose') }}
      </p>
    </div>

    <Dialog
      v-model:visible="createOpen"
      modal
      :header="t('catalog.create')"
      :style="{ width: '30rem' }"
    >
      <form
        class="form"
        @submit.prevent="createProduct"
      >
        <label for="product-code">{{ t('catalog.form.code') }}</label>
        <InputText
          id="product-code"
          v-model="draft.code"
          :invalid="!!errors.code"
          data-testid="new-product-code"
        />
        <small
          v-for="text in errors.code ?? []"
          :key="text"
          class="error"
        >{{ text }}</small>
        <label for="product-name">{{ t('catalog.form.name') }}</label>
        <InputText
          id="product-name"
          v-model="draft.name"
          :invalid="!!errors.name"
          data-testid="new-product-name"
        />
        <small
          v-for="text in errors.name ?? []"
          :key="text"
          class="error"
        >{{ text }}</small>
        <label for="product-subject">{{ t('catalog.form.subject') }}</label>
        <Select
          v-model="draft.subject_type"
          input-id="product-subject"
          :options="subjects"
          option-label="label"
          option-value="value"
        />
        <label for="product-metric">{{ t('catalog.form.metric') }}</label>
        <Select
          v-model="draft.default_metric_id"
          input-id="product-metric"
          :options="store.metrics"
          option-label="code"
          option-value="id"
          :invalid="!!errors.default_metric_id"
          data-testid="new-product-metric"
        />
        <small
          v-for="text in errors.default_metric_id ?? []"
          :key="text"
          class="error"
        >{{ text }}</small>
        <div class="actions">
          <Button
            :label="t('catalog.form.cancel')"
            severity="secondary"
            text
            @click="createOpen = false"
          />
          <Button
            type="submit"
            :label="t('catalog.form.save')"
            data-testid="new-product-save"
          />
        </div>
      </form>
    </Dialog>
  </section>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.split {
  display: grid;
  grid-template-columns: minmax(18rem, 1fr) 2fr;
  gap: 1.5rem;
}
.row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin: 0.5rem 0;
}
.edition {
  min-width: 8rem;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
.hint {
  color: var(--p-text-muted-color);
}
.error {
  color: var(--p-red-500);
}
</style>
