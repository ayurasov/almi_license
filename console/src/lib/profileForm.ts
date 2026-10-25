// Profile parameters <-> editor form (E07-06). Unknown keys of params (directives and the like)
// are kept as they are; the server validates the whole profile (table 8.2 of document 1).
export interface MessageForm {
  id: string
  state: string
  severity: string
  placement: string
  repeat: string
  ru: string
  en: string
}

export interface ProfileForm {
  enforcement: string
  notify_before_days: number | null
  grace_days: number | null
  expiry_action: string
  restricted_caps: string
  restricted_days: number | null
  hard_block_mode: string
  read_only_caps: string
  offline_grace_days: number | null
  check_interval_hours: number | null
  release_after_days: number | null
  reserve_pct: number | null
  messages: MessageForm[]
}

export type Params = Record<string, unknown>

export const NUMBER_FIELDS = [
  'notify_before_days',
  'grace_days',
  'restricted_days',
  'offline_grace_days',
  'check_interval_hours',
  'release_after_days',
  'reserve_pct',
] as const

// Section 10 of document 4, profile *.commercial.
export const DEFAULT_PARAMS: Params = {
  enforcement: 'monitor',
  notify_before_days: 30,
  grace_days: 14,
  expiry_action: 'restrict',
  restricted_caps: ['updates', 'macros', 'collaboration'],
  restricted_days: null,
  hard_block_mode: 'read_only',
  read_only_caps: ['view', 'export', 'print'],
  offline_grace_days: null,
  check_interval_hours: 24,
  release_after_days: 30,
  reserve_pct: 3,
}

function str(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function num(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

function list(value: unknown): string {
  return Array.isArray(value) ? value.filter((item) => typeof item === 'string').join(', ') : ''
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

export function toForm(params: Params): ProfileForm {
  const messages = Object.entries(record(params.messages)).map(([id, raw]) => {
    const message = record(raw)
    const text = record(message.text)
    return {
      id,
      state: str(message.state),
      severity: str(message.severity),
      placement: str(message.placement),
      repeat: str(message.repeat),
      ru: str(text.ru),
      en: str(text.en),
    }
  })
  return {
    enforcement: str(params.enforcement),
    notify_before_days: num(params.notify_before_days),
    grace_days: num(params.grace_days),
    expiry_action: str(params.expiry_action),
    restricted_caps: list(params.restricted_caps),
    restricted_days: num(params.restricted_days),
    hard_block_mode: str(params.hard_block_mode),
    read_only_caps: list(params.read_only_caps),
    offline_grace_days: num(params.offline_grace_days),
    check_interval_hours: num(params.check_interval_hours),
    release_after_days: num(params.release_after_days),
    reserve_pct: num(params.reserve_pct),
    messages,
  }
}

function codes(text: string): string[] {
  return text
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
}

export function toParams(form: ProfileForm, base: Params): Params {
  const params: Params = { ...base }
  params.enforcement = form.enforcement
  params.expiry_action = form.expiry_action
  params.hard_block_mode = form.hard_block_mode
  params.restricted_caps = codes(form.restricted_caps)
  params.read_only_caps = codes(form.read_only_caps)
  for (const field of NUMBER_FIELDS) params[field] = form[field]
  const messages: Record<string, unknown> = {}
  for (const message of form.messages) {
    if (!message.id.trim()) continue
    const text: Record<string, string> = {}
    if (message.ru) text.ru = message.ru
    if (message.en) text.en = message.en
    const entry: Record<string, unknown> = { text }
    for (const key of ['state', 'severity', 'placement', 'repeat'] as const) if (message[key]) entry[key] = message[key]
    messages[message.id.trim()] = entry
  }
  if (Object.keys(messages).length > 0) params.messages = messages
  else delete params.messages
  return params
}
