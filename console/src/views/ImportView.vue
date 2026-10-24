<script setup lang="ts">
// Import wizard (E07-07): upload → preview → article mapping → confirmation → report.
// Statuses and reasons come from the server preview (E06-01); keys are masks only.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Step from 'primevue/step'
import StepList from 'primevue/steplist'
import StepPanel from 'primevue/steppanel'
import StepPanels from 'primevue/steppanels'
import Stepper from 'primevue/stepper'
import Tag from 'primevue/tag'
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/problem'
import { useCatalogStore } from '@/stores/catalog'
import { type ImportError, type ImportRow, useImportsStore } from '@/stores/imports'

type Step = 'upload' | 'preview' | 'mapping' | 'confirm' | 'report'
const STEPS: Step[] = ['upload', 'preview', 'mapping', 'confirm', 'report']
const SEVERITY = { new: 'success', update: 'info', skip: 'secondary', error: 'danger' } as const

const { t, d } = useI18n()
const store = useImportsStore()
const catalog = useCatalogStore()
const step = ref<Step>('upload')
const selected = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const busy = ref(false)
const errors = ref<string[]>([])
const statusFilter = ref('')
const choice = reactive<Record<string, { product_id: string; edition_id: string; metric_id: string }>>({})

onMounted(() => {
  void catalog.load()
  void store.loadMappings()
})

const rows = computed<ImportRow[]>(() =>
  (store.preview?.rows ?? []).filter((row) => !statusFilter.value || row.status === statusFilter.value),
)
const filters = computed(() => [
  { value: '', label: t('imports.all') },
  ...(['new', 'update', 'skip', 'error'] as const).map((value) => ({ value, label: t(`imports.status.${value}`) })),
])

function editionsOf(productId: string): { id: string; code: string }[] {
  return catalog.products.find((product) => product.id === productId)?.editions ?? []
}

function field(row: ImportRow, name: string): string {
  const value = row.fields[name]
  return typeof value === 'string' || typeof value === 'number' ? String(value) : ''
}

async function run(action: () => Promise<unknown>): Promise<boolean> {
  busy.value = true
  errors.value = []
  try {
    await action()
    return true
  } catch (failure) {
    if (failure instanceof ApiError) {
      errors.value = failure.hasFieldErrors ? Object.values(failure.fieldErrors).flat() : [failure.message]
    } else errors.value = [t('errors.network')]
    return false
  } finally {
    busy.value = false
  }
}

function onFile(event: Event): void {
  const input = event.target as HTMLInputElement
  selected.value = input.files?.[0] ?? null
}

async function upload(): Promise<void> {
  const file = selected.value
  if (file && (await run(() => store.upload(file)))) step.value = 'preview'
}

function prepareMapping(): void {
  for (const aa of store.unmapped) {
    choice[aa] ??= { product_id: '', edition_id: '', metric_id: '' }
  }
  step.value = 'mapping'
}

function pickProduct(aa: string, productId: string): void {
  const product = catalog.products.find((item) => item.id === productId)
  choice[aa] = { product_id: productId, edition_id: '', metric_id: product?.default_metric_id ?? '' }
}

async function saveMapping(aa: string): Promise<void> {
  const value = choice[aa]
  if (!value) return
  await run(() =>
    store.saveMapping(aa, {
      product_id: value.product_id,
      edition_id: value.edition_id || null,
      metric_id: value.metric_id,
    }),
  )
}

async function recheck(): Promise<void> {
  if (await run(() => store.recheck())) step.value = 'preview'
}

async function apply(): Promise<void> {
  if (await run(() => store.apply())) step.value = 'report'
}

function restart(): void {
  store.reset()
  selected.value = null
  // The same file chosen again must fire change.
  if (fileInput.value) fileInput.value.value = ''
  step.value = 'upload'
}
</script>

<template>
  <section>
    <h1>{{ t('imports.title') }}</h1>
    <Message
      v-for="text in errors"
      :key="text"
      severity="error"
      data-testid="import-error"
    >
      {{ text }}
    </Message>

    <Stepper
      :value="step"
      linear
    >
      <StepList>
        <Step
          v-for="name in STEPS"
          :key="name"
          :value="name"
        >
          {{ t(`imports.steps.${name}`) }}
        </Step>
      </StepList>
      <StepPanels>
        <StepPanel value="upload">
          <p class="hint">
            {{ t('imports.hint') }}
          </p>
          <label for="import-file">{{ t('imports.choose') }}</label>
          <input
            id="import-file"
            ref="fileInput"
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            data-testid="import-file"
            @change="onFile"
          >
          <div class="actions">
            <Button
              :label="t('imports.upload')"
              :disabled="!selected"
              :loading="busy"
              data-testid="import-upload"
              @click="upload"
            />
          </div>
        </StepPanel>

        <StepPanel value="preview">
          <div
            v-if="store.preview"
            class="summary"
            data-testid="import-summary"
          >
            <Tag
              v-for="(count, kind) in store.preview.summary"
              :key="kind"
              :severity="SEVERITY[kind as keyof typeof SEVERITY] ?? 'secondary'"
              :value="`${t(`imports.summary.${kind}`)}: ${count}`"
              :data-testid="`summary-${kind}`"
            />
            <Select
              v-model="statusFilter"
              :options="filters"
              option-label="label"
              option-value="value"
              :aria-label="t('imports.filter')"
            />
          </div>
          <DataTable
            :value="rows"
            data-key="row"
            paginator
            :rows="20"
            size="small"
            data-testid="import-rows"
          >
            <Column
              field="row"
              :header="t('imports.columns.row')"
            />
            <Column :header="t('imports.columns.status')">
              <template #body="{ data }">
                <Tag
                  :value="t(`imports.status.${(data as ImportRow).status}`)"
                  :severity="SEVERITY[(data as ImportRow).status]"
                />
              </template>
            </Column>
            <Column :header="t('imports.columns.key')">
              <template #body="{ data }">
                <code>{{ field(data as ImportRow, 'key_mask') }}</code>
              </template>
            </Column>
            <Column :header="t('imports.columns.article')">
              <template #body="{ data }">
                {{ field(data as ImportRow, 'article') }}
              </template>
            </Column>
            <Column :header="t('imports.columns.inn')">
              <template #body="{ data }">
                {{ field(data as ImportRow, 'inn') }}
              </template>
            </Column>
            <Column :header="t('imports.columns.limit')">
              <template #body="{ data }">
                {{ field(data as ImportRow, 'limit') }}
              </template>
            </Column>
            <Column :header="t('imports.columns.validUntil')">
              <template #body="{ data }">
                <template v-if="field(data as ImportRow, 'valid_until')">
                  {{ d(new Date(field(data as ImportRow, 'valid_until'))) }}
                </template>
                <template v-else-if="field(data as ImportRow, 'type') === 'perpetual'">
                  {{ t('imports.perpetual') }}
                </template>
              </template>
            </Column>
            <Column :header="t('imports.columns.errors')">
              <template #body="{ data }">
                {{ (data as ImportRow).errors.join('; ') }}
              </template>
            </Column>
          </DataTable>
          <div class="actions">
            <Button
              :label="t('imports.back')"
              severity="secondary"
              text
              @click="restart"
            />
            <Button
              :label="t('imports.next')"
              data-testid="import-next"
              @click="store.unmapped.length > 0 ? prepareMapping() : (step = 'confirm')"
            />
          </div>
        </StepPanel>

        <StepPanel value="mapping">
          <p>{{ t('imports.mapping.intro') }}</p>
          <div
            v-for="aa in store.unmapped"
            :key="aa"
            class="mapping"
            :data-testid="`mapping-${aa}`"
          >
            <strong>{{ t('imports.mapping.aa') }} {{ aa }}</strong>
            <Select
              :model-value="choice[aa]?.product_id"
              :options="catalog.products"
              option-label="code"
              option-value="id"
              :placeholder="t('imports.mapping.product')"
              data-testid="mapping-product"
              @update:model-value="pickProduct(aa, $event as string)"
            />
            <Select
              v-if="choice[aa]"
              v-model="choice[aa].edition_id"
              :options="editionsOf(choice[aa].product_id)"
              option-label="code"
              option-value="id"
              show-clear
              :placeholder="t('imports.mapping.edition')"
            />
            <Select
              v-if="choice[aa]"
              v-model="choice[aa].metric_id"
              :options="catalog.metrics"
              option-label="code"
              option-value="id"
              :placeholder="t('imports.mapping.metric')"
            />
            <Button
              :label="t('imports.mapping.save')"
              :disabled="!choice[aa]?.product_id || !choice[aa]?.metric_id"
              data-testid="mapping-save"
              @click="saveMapping(aa)"
            />
            <i
              v-if="store.mappings.some((m) => m.aa === aa)"
              class="pi pi-check"
              :data-testid="`mapping-saved-${aa}`"
            />
          </div>
          <div class="actions">
            <Button
              :label="t('imports.next')"
              severity="secondary"
              text
              @click="step = 'confirm'"
            />
            <Button
              :label="t('imports.mapping.recheck')"
              :loading="busy"
              data-testid="import-recheck"
              @click="recheck"
            />
          </div>
        </StepPanel>

        <StepPanel value="confirm">
          <p
            v-if="store.preview"
            data-testid="import-confirm-text"
          >
            {{ t('imports.confirmText', store.preview.summary) }}
          </p>
          <div class="actions">
            <Button
              :label="t('imports.back')"
              severity="secondary"
              text
              @click="step = 'preview'"
            />
            <Button
              :label="t('imports.apply')"
              :loading="busy"
              data-testid="import-apply"
              @click="apply"
            />
          </div>
        </StepPanel>

        <StepPanel value="report">
          <dl
            v-if="store.report"
            class="report"
            data-testid="import-report"
          >
            <dt>{{ t('imports.report.created') }}</dt>
            <dd data-testid="report-created">
              {{ store.report.created }}
            </dd>
            <dt>{{ t('imports.report.updated') }}</dt>
            <dd>{{ store.report.updated }}</dd>
            <dt>{{ t('imports.report.skipped') }}</dt>
            <dd>{{ store.report.skipped }}</dd>
            <dt>{{ t('imports.report.customers') }}</dt>
            <dd>{{ store.report.customers_created }}</dd>
            <dt>{{ t('imports.report.errors') }}</dt>
            <dd>{{ store.report.errors.length }}</dd>
          </dl>
          <DataTable
            v-if="store.report && store.report.errors.length > 0"
            :value="store.report.errors"
            data-key="row"
            size="small"
          >
            <Column
              field="row"
              :header="t('imports.columns.row')"
            />
            <Column :header="t('imports.columns.errors')">
              <template #body="{ data }">
                {{ (data as ImportError).errors.join('; ') }}
              </template>
            </Column>
          </DataTable>
          <div class="actions">
            <Button
              :label="t('imports.report.again')"
              @click="restart"
            />
          </div>
        </StepPanel>
      </StepPanels>
    </Stepper>
  </section>
</template>

<style scoped>
.summary,
.mapping,
.actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin: 0.75rem 0;
}
.actions {
  justify-content: flex-end;
}
.report {
  display: grid;
  grid-template-columns: max-content auto;
  gap: 0.25rem 1rem;
}
.hint {
  color: var(--p-text-muted-color);
}
</style>
