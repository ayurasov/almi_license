<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import { useToast } from 'primevue/usetoast'
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/problem'
import { type CustomerForm, formErrors } from '@/lib/customerSchema'
import { type Customer, useCustomersStore } from '@/stores/customers'

const props = defineProps<{ customer: Customer | null }>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{ saved: [customer: Customer] }>()

const i18n = useI18n()
const { t } = i18n
const toast = useToast()
const store = useCustomersStore()
const form = reactive<CustomerForm>({ name: '', inn: '', external_id: '', status: 'active' })
const errors = ref<Record<string, string[]>>({})
const busy = ref(false)
const statuses = computed(() =>
  (['active', 'archived'] as const).map((value) => ({ value, label: t(`customers.status.${value}`) })),
)

watch(visible, (open) => {
  if (!open) return
  const source = props.customer
  Object.assign(form, {
    name: source?.name ?? '',
    inn: source?.inn ?? '',
    external_id: source?.external_id ?? '',
    status: source?.status ?? 'active',
  })
  errors.value = {}
})

// Client messages are i18n keys; server messages are already texts.
function message(text: string): string {
  return i18n.te(text) ? t(text) : text
}

async function save(): Promise<void> {
  errors.value = formErrors(form)
  if (Object.keys(errors.value).length > 0) return
  busy.value = true
  try {
    const saved = props.customer ? await store.update(props.customer.id, { ...form }) : await store.create({ ...form })
    toast.add({ severity: 'success', summary: t('customers.saved'), life: 3000 })
    visible.value = false
    emit('saved', saved)
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
    :header="customer ? t('customers.form.titleEdit') : t('customers.form.titleCreate')"
    :style="{ width: '32rem' }"
  >
    <form
      class="customer-form"
      @submit.prevent="save"
    >
      <label for="customer-name">{{ t('customers.form.name') }}</label>
      <InputText
        id="customer-name"
        v-model="form.name"
        :invalid="!!errors.name"
      />
      <small
        v-for="text in errors.name"
        :key="text"
        class="p-error"
      >{{ message(text) }}</small>

      <label for="customer-inn">{{ t('customers.form.inn') }}</label>
      <InputText
        id="customer-inn"
        v-model="form.inn"
        inputmode="numeric"
        :invalid="!!errors.inn"
      />
      <small
        v-for="text in errors.inn"
        :key="text"
        class="p-error"
      >{{ message(text) }}</small>

      <label for="customer-external-id">{{ t('customers.form.externalId') }}</label>
      <InputText
        id="customer-external-id"
        v-model="form.external_id"
        :invalid="!!errors.external_id"
      />
      <small
        v-for="text in errors.external_id"
        :key="text"
        class="p-error"
      >{{ message(text) }}</small>

      <label for="customer-status">{{ t('customers.form.status') }}</label>
      <Select
        v-model="form.status"
        input-id="customer-status"
        :options="statuses"
        option-label="label"
        option-value="value"
      />

      <Message
        v-for="text in errors.form"
        :key="text"
        severity="error"
      >
        {{ message(text) }}
      </Message>
      <div class="customer-form-actions">
        <Button
          type="button"
          :label="t('customers.form.cancel')"
          severity="secondary"
          @click="visible = false"
        />
        <Button
          type="submit"
          :label="t('customers.form.save')"
          :loading="busy"
        />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.customer-form {
  display: grid;
  gap: 0.4rem;
}
.customer-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
</style>
