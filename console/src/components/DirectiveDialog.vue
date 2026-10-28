<script setup lang="ts">
// A directive of the server for one activation or for every active activation of a licence
// (section 8 of document 2): the product runs it at its next check.
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/problem'
import { DIRECTIVE_TYPES, type DirectiveType, useActivationsStore } from '@/stores/activations'
import { useLicensesStore } from '@/stores/licenses'

const props = defineProps<{ target: { kind: 'activation' | 'license'; id: string } | null }>()
const emit = defineEmits<{ close: []; sent: [] }>()
const { t } = useI18n()
const toast = useToast()
const activations = useActivationsStore()
const licenses = useLicensesStore()
interface DirectiveForm {
  type: DirectiveType
  hours: number | null
  url: string
  fallbackDays: number | null
  textRu: string
  textEn: string
  severity: string
  placement: string
  repeat: string
  reason: string
}
const form = reactive<DirectiveForm>({
  type: 'refresh_now',
  hours: 24,
  url: '',
  fallbackDays: 14,
  textRu: '',
  textEn: '',
  severity: 'info',
  placement: 'dialog',
  repeat: 'once',
  reason: '',
})
const errors = ref<string[]>([])
const busy = ref(false)

const typeOptions = computed(() => DIRECTIVE_TYPES.map((value) => ({ value, label: t(`directives.type.${value}`) })))
const option = (group: string, values: string[]) =>
  values.map((value) => ({ value, label: t(`directives.${group}.${value}`) }))

watch(
  () => props.target,
  (target) => {
    if (target === null) return
    Object.assign(form, { type: 'refresh_now', hours: 24, url: '', fallbackDays: 14, textRu: '', textEn: '' })
    Object.assign(form, { severity: 'info', placement: 'dialog', repeat: 'once', reason: '' })
    errors.value = []
  },
)

function params(): Record<string, unknown> {
  switch (form.type) {
    case 'set_check_interval':
      return { hours: form.hours }
    case 'set_server_url':
      return { url: form.url.trim(), fallback_days: form.fallbackDays }
    case 'show_message':
      return {
        message: {
          severity: form.severity,
          placement: form.placement,
          repeat: form.repeat,
          text: { ru: form.textRu.trim(), ...(form.textEn.trim() ? { en: form.textEn.trim() } : {}) },
        },
      }
    case 'rebind':
    case 'release':
      return { reason: form.reason.trim() }
    default:
      return {}
  }
}

async function send(): Promise<void> {
  if (props.target === null) return
  busy.value = true
  errors.value = []
  try {
    const body = { type: form.type, params: params() }
    if (props.target.kind === 'activation') {
      await activations.sendDirective(props.target.id, body)
      toast.add({ severity: 'success', summary: t('directives.sent'), life: 3000 })
    } else {
      const queued = await licenses.sendDirective(props.target.id, body)
      toast.add({ severity: 'success', summary: t('directives.sentMany', { count: queued }), life: 3000 })
    }
    emit('sent')
  } catch (failure) {
    errors.value =
      failure instanceof ApiError ? Object.values(failure.fieldErrors).flat() : [t('errors.network')]
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog
    :visible="target !== null"
    modal
    :header="target?.kind === 'license' ? t('directives.titleLicense') : t('directives.title')"
    :style="{ width: '34rem' }"
    @update:visible="emit('close')"
  >
    <form
      class="directive-form"
      data-testid="directive-form"
      @submit.prevent="send"
    >
      <Message severity="info">
        {{ t('directives.hint') }}
      </Message>
      <label for="directive-type">{{ t('directives.typeLabel') }}</label>
      <Select
        v-model="form.type"
        input-id="directive-type"
        :options="typeOptions"
        option-label="label"
        option-value="value"
        data-testid="directive-type"
      />
      <small class="explain">{{ t(`directives.explain.${form.type}`) }}</small>

      <template v-if="form.type === 'set_check_interval'">
        <label for="directive-hours">{{ t('directives.hours') }}</label>
        <InputNumber
          v-model="form.hours"
          input-id="directive-hours"
          :min="1"
          :max="720"
        />
      </template>

      <template v-if="form.type === 'set_server_url'">
        <label for="directive-url">{{ t('directives.url') }}</label>
        <InputText
          id="directive-url"
          v-model="form.url"
          placeholder="https://license.corp.local"
          data-testid="directive-url"
        />
        <label for="directive-fallback">{{ t('directives.fallbackDays') }}</label>
        <InputNumber
          v-model="form.fallbackDays"
          input-id="directive-fallback"
          :min="1"
          :max="90"
        />
      </template>

      <template v-if="form.type === 'show_message'">
        <label for="directive-text-ru">{{ t('directives.textRu') }}</label>
        <Textarea
          id="directive-text-ru"
          v-model="form.textRu"
          rows="3"
          :maxlength="400"
          data-testid="directive-text"
        />
        <label for="directive-text-en">{{ t('directives.textEn') }}</label>
        <Textarea
          id="directive-text-en"
          v-model="form.textEn"
          rows="2"
          :maxlength="400"
        />
        <div class="row">
          <Select
            v-model="form.severity"
            :options="option('severity', ['info', 'warning', 'critical'])"
            option-label="label"
            option-value="value"
            :aria-label="t('directives.severityLabel')"
          />
          <Select
            v-model="form.placement"
            :options="option('placement', ['banner', 'dialog', 'about', 'tray'])"
            option-label="label"
            option-value="value"
            :aria-label="t('directives.placementLabel')"
          />
          <Select
            v-model="form.repeat"
            :options="option('repeat', ['once', 'daily', 'each_start'])"
            option-label="label"
            option-value="value"
            :aria-label="t('directives.repeatLabel')"
          />
        </div>
      </template>

      <template v-if="form.type === 'rebind' || form.type === 'release'">
        <label for="directive-reason">{{ t('directives.reason') }}</label>
        <InputText
          id="directive-reason"
          v-model="form.reason"
        />
      </template>

      <small
        v-for="message in errors"
        :key="message"
        class="p-error"
      >{{ message }}</small>
      <div class="buttons">
        <Button
          type="button"
          :label="t('directives.cancel')"
          severity="secondary"
          @click="emit('close')"
        />
        <Button
          type="submit"
          :label="t('directives.send')"
          :loading="busy"
          data-testid="directive-send"
        />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.directive-form {
  display: grid;
  gap: 0.4rem;
}
.explain {
  color: var(--p-text-muted-color);
}
.row {
  display: flex;
  gap: 0.5rem;
}
.buttons {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
