<script setup lang="ts">
// Console users (E07-09): an ALMI administrator creates users, changes roles, blocks them and
// resets passwords. A generated password is shown once and forgotten when the dialog closes.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api/problem'
import { type Account, type ManagedRole, useAccountsStore } from '@/stores/accounts'
import { DEFAULT_QUERY, useCustomersStore } from '@/stores/customers'
import { useSessionStore } from '@/stores/session'

const { t, d } = useI18n()
const toast = useToast()
const store = useAccountsStore()
const session = useSessionStore()
const createOpen = ref(false)
const customers = useCustomersStore()
const draft = reactive<{ username: string; role: ManagedRole; customerId: string }>({
  username: '',
  role: 'operator',
  customerId: '',
})
const errors = ref<Record<string, string[]>>({})
const confirming = ref<{ kind: 'reset' | 'block'; account: Account } | null>(null)
const issued = ref<{ username: string; password: string } | null>(null)

const staffRoles = computed(() =>
  (['operator', 'admin'] as const).map((value) => ({ value, label: t(`users.role.${value}`) })),
)
const roles = computed(() => [...staffRoles.value, { value: 'customer_viewer' as const, label: t('users.role.customer_viewer') }])
const customerOptions = computed(() => customers.items.map((customer) => ({ value: customer.id, label: customer.name })))

function customerName(id: string | null): string {
  return customers.items.find((customer) => customer.id === id)?.name ?? ''
}

onMounted(() => {
  void store.list()
  void customers.list({ ...DEFAULT_QUERY, pageSize: 100 })
})

function isSelf(account: Account): boolean {
  return account.username === session.user?.username
}

function locked(account: Account): boolean {
  return account.locked_until !== null && new Date(account.locked_until) > new Date()
}

async function run(action: () => Promise<unknown>): Promise<boolean> {
  errors.value = {}
  try {
    await action()
    return true
  } catch (failure) {
    if (failure instanceof ApiError && failure.hasFieldErrors) errors.value = failure.fieldErrors
    else if (!(failure instanceof ApiError)) errors.value = { form: [t('errors.network')] }
    return false
  }
}

async function create(): Promise<void> {
  await run(async () => {
    const customer = draft.role === 'customer_viewer' ? draft.customerId : undefined
    const result = await store.create(draft.username.trim(), draft.role, customer)
    createOpen.value = false
    issued.value = { username: result.account.username, password: result.password }
    Object.assign(draft, { username: '', role: 'operator', customerId: '' })
  })
}

async function changeRole(account: Account, role: ManagedRole): Promise<void> {
  if (await run(() => store.update(account.username, { role }))) {
    toast.add({ severity: 'success', summary: t('users.saved'), life: 3000 })
  }
}

async function confirm(): Promise<void> {
  const pending = confirming.value
  if (!pending) return
  confirming.value = null
  if (pending.kind === 'block') {
    await run(() => store.update(pending.account.username, { active: false }))
    return
  }
  await run(async () => {
    const result = await store.resetPassword(pending.account.username)
    issued.value = { username: result.account.username, password: result.password }
  })
}
</script>

<template>
  <section>
    <div class="toolbar">
      <h1>{{ t('users.title') }}</h1>
      <Button
        :label="t('users.create')"
        icon="pi pi-plus"
        data-testid="user-create"
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
        @click="store.list()"
      />
    </Message>
    <Message
      v-for="text in [...(errors.form ?? []), ...(createOpen ? [] : (errors.username ?? []))]"
      :key="text"
      severity="error"
    >
      {{ text }}
    </Message>

    <DataTable
      :value="store.items"
      :loading="store.loading"
      data-key="username"
      data-testid="users-table"
    >
      <template #empty>
        {{ t('users.empty') }}
      </template>
      <Column
        field="username"
        :header="t('users.columns.username')"
      />
      <Column :header="t('users.columns.role')">
        <template #body="{ data }">
          <Select
            v-if="(data as Account).role !== 'customer_viewer' && !isSelf(data as Account)"
            :model-value="(data as Account).role"
            :options="staffRoles"
            option-label="label"
            option-value="value"
            :aria-label="t('users.columns.role')"
            @update:model-value="changeRole(data as Account, $event as ManagedRole)"
          />
          <span v-else>{{ t(`users.role.${(data as Account).role}`) }}</span>
          <small
            v-if="(data as Account).customer_id"
            class="customer"
          > — {{ customerName((data as Account).customer_id) }}</small>
        </template>
      </Column>
      <Column :header="t('users.columns.status')">
        <template #body="{ data }">
          <Tag
            v-if="!(data as Account).active"
            :value="t('users.status.blocked')"
            severity="danger"
          />
          <Tag
            v-else-if="locked(data as Account)"
            :value="t('users.status.locked', { until: d(new Date((data as Account).locked_until ?? '')) })"
            severity="warn"
          />
          <Tag
            v-else
            :value="t('users.status.active')"
            severity="success"
          />
        </template>
      </Column>
      <Column :header="t('users.columns.lastLogin')">
        <template #body="{ data }">
          {{ (data as Account).last_login ? d(new Date((data as Account).last_login ?? '')) : t('users.never') }}
        </template>
      </Column>
      <Column>
        <template #body="{ data }">
          <template v-if="!isSelf(data as Account)">
            <Button
              v-if="(data as Account).active"
              text
              size="small"
              severity="danger"
              :label="t('users.block')"
              data-testid="user-block"
              @click="confirming = { kind: 'block', account: data as Account }"
            />
            <Button
              v-else
              text
              size="small"
              :label="t('users.unblock')"
              data-testid="user-unblock"
              @click="run(() => store.update((data as Account).username, { active: true }))"
            />
            <Button
              text
              size="small"
              :label="t('users.reset')"
              data-testid="user-reset"
              @click="confirming = { kind: 'reset', account: data as Account }"
            />
          </template>
        </template>
      </Column>
    </DataTable>

    <Dialog
      v-model:visible="createOpen"
      modal
      :header="t('users.create')"
      :style="{ width: '26rem' }"
    >
      <form
        class="form"
        @submit.prevent="create"
      >
        <label for="user-username">{{ t('users.form.username') }}</label>
        <InputText
          id="user-username"
          v-model="draft.username"
          :invalid="!!errors.username"
          autocomplete="off"
          data-testid="user-username"
        />
        <small
          v-for="text in errors.username ?? []"
          :key="text"
          class="error"
        >{{ text }}</small>
        <label for="user-role">{{ t('users.form.role') }}</label>
        <Select
          v-model="draft.role"
          input-id="user-role"
          :options="roles"
          option-label="label"
          option-value="value"
          data-testid="user-role"
        />
        <template v-if="draft.role === 'customer_viewer'">
          <label for="user-customer">{{ t('users.form.customer') }}</label>
          <Select
            v-model="draft.customerId"
            input-id="user-customer"
            :options="customerOptions"
            option-label="label"
            option-value="value"
            filter
            :invalid="!!errors.customer_id"
            data-testid="user-customer"
          />
          <small
            v-for="text in errors.customer_id ?? []"
            :key="text"
            class="error"
          >{{ text }}</small>
        </template>
        <div class="actions">
          <Button
            :label="t('users.form.cancel')"
            severity="secondary"
            text
            @click="createOpen = false"
          />
          <Button
            type="submit"
            :label="t('users.form.save')"
            data-testid="user-save"
          />
        </div>
      </form>
    </Dialog>

    <Dialog
      :visible="confirming !== null"
      modal
      :closable="false"
      :header="confirming?.kind === 'reset' ? t('users.reset') : t('users.block')"
      :style="{ width: '28rem' }"
    >
      <p>
        {{
          confirming?.kind === 'reset'
            ? t('users.confirmReset', { username: confirming.account.username })
            : t('users.confirmBlock', { username: confirming?.account.username ?? '' })
        }}
      </p>
      <div class="actions">
        <Button
          :label="t('users.form.cancel')"
          severity="secondary"
          text
          @click="confirming = null"
        />
        <Button
          :label="t('users.confirm')"
          severity="danger"
          data-testid="user-confirm"
          @click="confirm"
        />
      </div>
    </Dialog>

    <Dialog
      :visible="issued !== null"
      modal
      :closable="false"
      :header="t('users.password.title', { username: issued?.username ?? '' })"
      :style="{ width: '28rem' }"
    >
      <Message severity="warn">
        {{ t('users.password.once') }}
      </Message>
      <p class="password">
        <code data-testid="issued-password">{{ issued?.password }}</code>
      </p>
      <Button
        :label="t('users.password.close')"
        data-testid="issued-password-close"
        @click="issued = null"
      />
    </Dialog>
  </section>
</template>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
  margin-top: 1rem;
}
.password code {
  font-size: 1.25rem;
  user-select: all;
}
.error {
  color: var(--p-red-500);
}
</style>
