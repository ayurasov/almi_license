<script setup lang="ts">
// Actions of the license card (E07-04): every action goes through this confirmation dialog;
// revoke, suspend, lift block and transfer need a reason (prompt I3-01).
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import DatePicker from 'primevue/datepicker'
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
import { DEFAULT_QUERY, useCustomersStore } from '@/stores/customers'
import { type License, type LicenseAction, useLicensesStore } from '@/stores/licenses'

const props = defineProps<{ license: License; action: LicenseAction | null }>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{ done: [license: License] }>()

const { t } = useI18n()
const toast = useToast()
const store = useLicensesStore()
const customers = useCustomersStore()
const form = reactive({
  reason: '',
  until: null as Date | null,
  validUntil: null as Date | null,
  supportUntil: null as Date | null,
  limit: null as number | null,
  reservePct: null as number | null,
  enforcement: '',
  userLimit: null as number | null,
  onlyActive: false,
  maxVersion: '',
  customerId: '',
  document: '',
})
const errors = ref<Record<string, string[]>>({})
const busy = ref(false)

const needsReason = computed(() => props.action !== null && props.action !== 'renew' && props.action !== 'settings')
const enforcementOptions = computed(() =>
  (['', 'enforce', 'monitor'] as const).map((value) => ({
    value,
    label: t(`licenses.enforcement.${value || 'profile'}`),
  })),
)
const customerOptions = computed(() =>
  customers.items
    .filter((customer) => customer.id !== props.license.customer_id)
    .map((customer) => ({ value: customer.id, label: customer.name })),
)

watch(visible, (open) => {
  if (!open) return
  const date = (value: string | null | undefined) => (value ? new Date(value) : null)
  Object.assign(form, {
    reason: '',
    until: null,
    validUntil: date(props.license.valid_until),
    supportUntil: date(props.license.support_until),
    limit: props.license.limit,
    reservePct: props.license.reserve_pct,
    enforcement: props.license.enforcement,
    userLimit: props.license.limits.named_users ?? props.license.limits.active_users ?? null,
    onlyActive: props.license.limits.only_count_active,
    maxVersion: props.license.max_product_version,
    customerId: '',
    document: '',
  })
  errors.value = {}
  if (props.action === 'transfer') void customers.list({ ...DEFAULT_QUERY, pageSize: 100, status: 'active' })
})

function iso(value: Date | null): string | null {
  return value ? value.toISOString() : null
}

async function run(): Promise<License> {
  const id = props.license.id
  switch (props.action) {
    case 'renew':
      return store.renew(id, {
        valid_until: iso(form.validUntil),
        support_until: iso(form.supportUntil),
        limit: form.limit,
      })
    case 'suspend':
    case 'resume':
    case 'revoke':
      return store.setStatus(id, props.action, form.reason)
    case 'liftBlock':
      return store.liftBlock(id, iso(form.until) ?? '', form.reason)
    case 'settings':
      return store.updateSettings(id, {
        limit: form.limit ?? undefined,
        reserve_pct: form.reservePct,
        enforcement: form.enforcement,
        limits: userLimits(),
        max_product_version: form.maxVersion.trim(),
      })
    case 'transfer':
      return store.transfer(id, { customer_id: form.customerId, reason: form.reason, document: form.document })
    case null:
      throw new Error('no action')
  }
}

// A server product counts named or only active users against one limit (E11-01).
function userLimits(): { named_users?: number; active_users?: number; only_count_active: boolean } {
  if (form.userLimit === null) return { only_count_active: false }
  return form.onlyActive
    ? { active_users: form.userLimit, only_count_active: true }
    : { named_users: form.userLimit, only_count_active: false }
}

async function confirm(): Promise<void> {
  busy.value = true
  errors.value = {}
  try {
    const license = await run()
    toast.add({ severity: 'success', summary: t('licenses.done'), life: 3000 })
    visible.value = false
    emit('done', license)
  } catch (failure) {
    if (failure instanceof ApiError && failure.hasFieldErrors) errors.value = failure.fieldErrors
    else if (!(failure instanceof ApiError)) errors.value = { form: [t('errors.network')] }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    :header="action ? t(`licenses.actions.${action}`) : ''"
    :style="{ width: '32rem' }"
  >
    <form
      class="action-form"
      @submit.prevent="confirm"
    >
      <Message
        v-if="action === 'revoke'"
        severity="warn"
      >
        {{ t('licenses.dialog.revokeWarning') }}
      </Message>

      <template v-if="action === 'renew'">
        <label for="action-valid-until">{{ t('licenses.dialog.validUntil') }}</label>
        <DatePicker
          v-model="form.validUntil"
          input-id="action-valid-until"
          show-time
          show-button-bar
        />
        <label for="action-support-until">{{ t('licenses.dialog.supportUntil') }}</label>
        <DatePicker
          v-model="form.supportUntil"
          input-id="action-support-until"
          show-time
          show-button-bar
        />
      </template>

      <template v-if="action === 'renew' || action === 'settings'">
        <label for="action-limit">{{ t('licenses.dialog.limit') }}</label>
        <InputNumber
          v-model="form.limit"
          input-id="action-limit"
          :min="1"
        />
      </template>

      <template v-if="action === 'settings'">
        <label for="action-reserve">{{ t('licenses.dialog.reservePct') }}</label>
        <InputNumber
          v-model="form.reservePct"
          input-id="action-reserve"
          :min="0"
          :max="100"
        />
        <label for="action-enforcement">{{ t('licenses.dialog.enforcement') }}</label>
        <Select
          v-model="form.enforcement"
          input-id="action-enforcement"
          :options="enforcementOptions"
          option-label="label"
          option-value="value"
        />
        <label for="action-users">{{ t('licenses.dialog.userLimit') }}</label>
        <InputNumber
          v-model="form.userLimit"
          input-id="action-users"
          :min="1"
          data-testid="action-user-limit"
        />
        <div class="check">
          <Checkbox
            v-model="form.onlyActive"
            input-id="action-only-active"
            binary
          />
          <label for="action-only-active">{{ t('licenses.dialog.onlyActive') }}</label>
        </div>
        <label for="action-max-version">{{ t('licenses.dialog.maxVersion') }}</label>
        <InputText
          id="action-max-version"
          v-model="form.maxVersion"
          :placeholder="t('licenses.dialog.maxVersionHint')"
          data-testid="action-max-version"
        />
      </template>

      <template v-if="action === 'liftBlock'">
        <label for="action-until">{{ t('licenses.dialog.until') }}</label>
        <DatePicker
          v-model="form.until"
          input-id="action-until"
          show-time
        />
      </template>

      <template v-if="action === 'transfer'">
        <label for="action-customer">{{ t('licenses.dialog.customer') }}</label>
        <Select
          v-model="form.customerId"
          input-id="action-customer"
          :options="customerOptions"
          option-label="label"
          option-value="value"
          filter
        />
        <label for="action-document">{{ t('licenses.dialog.document') }}</label>
        <InputText
          id="action-document"
          v-model="form.document"
        />
      </template>

      <template v-if="needsReason">
        <label for="action-reason">{{ t('licenses.dialog.reason') }}</label>
        <Textarea
          id="action-reason"
          v-model="form.reason"
          rows="3"
          :invalid="!!errors.reason"
        />
      </template>

      <template
        v-for="(messages, field) in errors"
        :key="field"
      >
        <small
          v-for="message in messages"
          :key="message"
          class="p-error"
        >{{ message }}</small>
      </template>

      <div class="action-buttons">
        <Button
          type="button"
          :label="t('licenses.dialog.cancel')"
          severity="secondary"
          @click="visible = false"
        />
        <Button
          type="submit"
          :label="t('licenses.dialog.confirm')"
          :severity="action === 'revoke' ? 'danger' : undefined"
          :loading="busy"
          data-testid="action-confirm"
        />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.action-form {
  display: grid;
  gap: 0.4rem;
}
.check {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.action-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
</style>
