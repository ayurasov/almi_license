<script setup lang="ts">
// Policy profiles (E07-06, E01-03): a save is a new version; the history can be used as a base.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/problem'
import MessageEditor from '@/components/MessageEditor.vue'
import { DEFAULT_PARAMS, NUMBER_FIELDS, type Params, type ProfileForm, toForm, toParams } from '@/lib/profileForm'
import { type Profile, useProfilesStore } from '@/stores/profiles'

const { t, d } = useI18n()
const toast = useToast()
const store = useProfilesStore()
const code = ref('')
const isNew = ref(false)
const base = ref<Params>({})
const form = ref<ProfileForm | null>(null)
const errors = ref<Record<string, string[]>>({})
const busy = ref(false)

const options = (values: string[]) => computed(() => values.map((value) => ({ value, label: t(`profiles.options.${value}`) })))
const enforcements = options(['enforce', 'monitor'])
const expiryActions = options(['none', 'restrict', 'block'])
const blockModes = options(['read_only', 'no_start'])

onMounted(() => void store.list())

function edit(params: Params): void {
  base.value = params
  form.value = toForm(params)
  errors.value = {}
}

async function open(profile: Profile): Promise<void> {
  code.value = profile.code
  isNew.value = false
  edit(profile.params)
  await store.history(profile.code)
}

function create(): void {
  code.value = ''
  isNew.value = true
  store.versions = []
  edit({ ...DEFAULT_PARAMS })
}

async function save(): Promise<void> {
  if (!form.value) return
  busy.value = true
  errors.value = {}
  const latest = store.versions[0]?.version ?? 0
  try {
    const saved = await store.save(code.value.trim(), toParams(form.value, base.value))
    toast.add({
      severity: 'success',
      summary: saved.version === latest ? t('profiles.unchanged') : t('profiles.saved', { version: saved.version }),
      life: 3000,
    })
    isNew.value = false
    edit(saved.params)
  } catch (failure) {
    if (failure instanceof ApiError && failure.hasFieldErrors) errors.value = failure.fieldErrors
    else if (!(failure instanceof ApiError)) errors.value = { form: [t('errors.network')] }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section>
    <div class="toolbar">
      <h1>{{ t('profiles.title') }}</h1>
      <Button
        :label="t('profiles.create')"
        icon="pi pi-plus"
        data-testid="profile-create"
        @click="create"
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
        @click="store.list()"
      />
    </Message>

    <div class="split">
      <DataTable
        :value="store.items"
        :loading="store.loading"
        data-key="code"
        selection-mode="single"
        :selection="store.items.find((p) => p.code === code)"
        data-testid="profiles-table"
        @row-select="open($event.data as Profile)"
      >
        <template #empty>
          {{ t('profiles.empty') }}
        </template>
        <Column
          field="code"
          :header="t('profiles.columns.code')"
        />
        <Column
          field="version"
          :header="t('profiles.columns.version')"
        />
      </DataTable>

      <form
        v-if="form"
        class="editor"
        data-testid="profile-editor"
        @submit.prevent="save"
      >
        <Message
          v-for="text in errors.form ?? []"
          :key="text"
          severity="error"
        >
          {{ text }}
        </Message>
        <label for="profile-code">{{ t('profiles.columns.code') }}</label>
        <InputText
          id="profile-code"
          v-model="code"
          :disabled="!isNew"
          :invalid="!!errors.code"
          :placeholder="t('profiles.codeHint')"
          data-testid="profile-code"
        />
        <small
          v-for="text in errors.code ?? []"
          :key="text"
          class="error"
        >{{ text }}</small>

        <div class="grid">
          <label for="p-enforcement">{{ t('profiles.fields.enforcement') }}</label>
          <Select
            v-model="form.enforcement"
            input-id="p-enforcement"
            :options="enforcements"
            option-label="label"
            option-value="value"
            :invalid="!!errors.enforcement"
          />
          <label for="p-expiry">{{ t('profiles.fields.expiry_action') }}</label>
          <Select
            v-model="form.expiry_action"
            input-id="p-expiry"
            :options="expiryActions"
            option-label="label"
            option-value="value"
            :invalid="!!errors.expiry_action"
          />
          <label for="p-block">{{ t('profiles.fields.hard_block_mode') }}</label>
          <Select
            v-model="form.hard_block_mode"
            input-id="p-block"
            :options="blockModes"
            option-label="label"
            option-value="value"
            :invalid="!!errors.hard_block_mode"
          />
          <template
            v-for="field in NUMBER_FIELDS"
            :key="field"
          >
            <label :for="`p-${field}`">{{ t(`profiles.fields.${field}`) }}</label>
            <div>
              <InputNumber
                v-model="form[field]"
                :input-id="`p-${field}`"
                :use-grouping="false"
                :invalid="!!errors[field]"
                :data-testid="`profile-${field}`"
              />
              <small
                v-for="text in errors[field] ?? []"
                :key="text"
                class="error"
              >{{ text }}</small>
            </div>
          </template>
          <label for="p-restricted">{{ t('profiles.fields.restricted_caps') }}</label>
          <InputText
            id="p-restricted"
            v-model="form.restricted_caps"
            :placeholder="t('profiles.capsHint')"
            :invalid="!!errors.restricted_caps"
          />
          <label for="p-readonly">{{ t('profiles.fields.read_only_caps') }}</label>
          <InputText
            id="p-readonly"
            v-model="form.read_only_caps"
            :placeholder="t('profiles.capsHint')"
            :invalid="!!errors.read_only_caps"
          />
        </div>

        <MessageEditor v-model="form.messages" />
        <small
          v-for="text in errors.messages ?? []"
          :key="text"
          class="error"
        >{{ text }}</small>

        <div class="actions">
          <Button
            type="submit"
            :label="t('profiles.save')"
            :loading="busy"
            data-testid="profile-save"
          />
        </div>

        <h3>{{ t('profiles.history') }}</h3>
        <DataTable
          :value="store.versions"
          data-key="version"
          size="small"
          data-testid="profile-history"
        >
          <Column
            field="version"
            :header="t('profiles.columns.version')"
          />
          <Column :header="t('profiles.columns.createdAt')">
            <template #body="{ data }">
              {{ d(new Date((data as Profile).created_at)) }}
            </template>
          </Column>
          <Column>
            <template #body="{ data }">
              <Button
                text
                size="small"
                :label="t('profiles.load')"
                @click="edit((data as Profile).params)"
              />
            </template>
          </Column>
        </DataTable>
      </form>
      <p
        v-else
        class="hint"
      >
        {{ t('profiles.choose') }}
      </p>
    </div>
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
  grid-template-columns: minmax(16rem, 1fr) 2fr;
  gap: 1.5rem;
}
.editor {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.grid {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.5rem 1rem;
  align-items: center;
}
.actions {
  display: flex;
  justify-content: flex-end;
}
.hint {
  color: var(--p-text-muted-color);
}
.error {
  color: var(--p-red-500);
  display: block;
}
</style>
