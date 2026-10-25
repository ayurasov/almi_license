<script setup lang="ts">
// Message editor of a profile (E07-06): overrides of the default texts by id with a preview of
// the substitutions the product fills (section 9 of document 2).
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import { useI18n } from 'vue-i18n'

import { preview, type Sample, SUBSTITUTIONS, unknownSubstitutions } from '@/lib/messagePreview'
import type { MessageForm } from '@/lib/profileForm'

const messages = defineModel<MessageForm[]>({ required: true })
const { t, d } = useI18n()

const STATES = ['', 'TRIAL', 'UNLICENSED', 'ACTIVE', 'NOTICE', 'GRACE', 'RESTRICTED', 'BLOCKED', 'REVOKED']
const SEVERITIES = ['', 'info', 'warning', 'critical']
const PLACEMENTS = ['', 'banner', 'dialog', 'about', 'tray']
const REPEATS = ['', 'once', 'daily', 'each_start']

// Sample values only for the preview; they are not saved.
const sample: Sample = {
  days_left: '7',
  valid_until: d(new Date(Date.UTC(2027, 9, 31))),
  customer: 'ООО «Пример»',
  used: '42',
  limit: '50',
  product: 'АльтерОфис',
  support_contact: 'support.example',
}

function add(): void {
  messages.value.push({ id: '', state: '', severity: 'info', placement: 'banner', repeat: '', ru: '', en: '' })
}

function remove(index: number): void {
  messages.value.splice(index, 1)
}
</script>

<template>
  <div class="messages">
    <div class="head">
      <h3>{{ t('profiles.messages.title') }}</h3>
      <Button
        icon="pi pi-plus"
        :label="t('profiles.messages.add')"
        text
        data-testid="message-add"
        @click="add"
      />
    </div>
    <p
      v-if="messages.length === 0"
      class="hint"
    >
      {{ t('profiles.messages.empty') }}
    </p>
    <p class="hint">
      {{ t('profiles.messages.substitutions') }}: {{ SUBSTITUTIONS.join(', ') }}
    </p>
    <div
      v-for="(message, index) in messages"
      :key="index"
      class="message"
      :data-testid="`message-${index}`"
    >
      <div class="row">
        <InputText
          v-model="message.id"
          :placeholder="t('profiles.messages.id')"
          data-testid="message-id"
        />
        <Select
          v-model="message.state"
          :options="STATES"
          :placeholder="t('profiles.messages.state')"
        />
        <Select
          v-model="message.severity"
          :options="SEVERITIES"
          :placeholder="t('profiles.messages.severity')"
        />
        <Select
          v-model="message.placement"
          :options="PLACEMENTS"
          :placeholder="t('profiles.messages.placement')"
        />
        <Select
          v-model="message.repeat"
          :options="REPEATS"
          :placeholder="t('profiles.messages.repeat')"
        />
        <Button
          icon="pi pi-trash"
          text
          severity="danger"
          :aria-label="t('profiles.messages.remove')"
          @click="remove(index)"
        />
      </div>
      <Textarea
        v-model="message.ru"
        rows="2"
        :placeholder="t('profiles.messages.textRu')"
        data-testid="message-ru"
      />
      <Textarea
        v-model="message.en"
        rows="2"
        :placeholder="t('profiles.messages.textEn')"
      />
      <Message
        v-if="unknownSubstitutions(message.ru + message.en).length > 0"
        severity="warn"
        size="small"
      >
        {{ t('profiles.messages.unknown', { names: unknownSubstitutions(message.ru + message.en).join(', ') }) }}
      </Message>
      <div
        class="preview"
        data-testid="message-preview"
      >
        <strong>{{ t('profiles.messages.preview') }}:</strong>
        {{ preview(message.ru, sample) }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.head,
.row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.message {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  margin-bottom: 0.75rem;
  border: 1px solid var(--p-content-border-color);
  border-radius: 0.5rem;
}
.preview {
  padding: 0.5rem;
  background: var(--p-content-hover-background);
}
.hint {
  color: var(--p-text-muted-color);
}
</style>
