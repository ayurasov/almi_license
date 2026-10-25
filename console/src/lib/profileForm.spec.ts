import { describe, expect, it } from 'vitest'

import { DEFAULT_PARAMS, toForm, toParams } from './profileForm'

describe('profile form', () => {
  it('round-trips the parameters and keeps unknown keys', () => {
    const params = { ...DEFAULT_PARAMS, directives: [{ id: 'd1', type: 'collect_diagnostics' }] }
    expect(toParams(toForm(params), params)).toEqual(params)
  })

  it('parses capability lists and builds messages by id', () => {
    const form = toForm(DEFAULT_PARAMS)
    form.restricted_caps = ' updates ,macros,, '
    form.messages.push({ id: 'notice.banner', state: 'NOTICE', severity: '', placement: 'banner', repeat: '', ru: 'Осталось {days_left}', en: '' })
    form.messages.push({ id: ' ', state: '', severity: '', placement: '', repeat: '', ru: 'пусто', en: '' })

    const params = toParams(form, DEFAULT_PARAMS)

    expect(params.restricted_caps).toEqual(['updates', 'macros'])
    expect(params.messages).toEqual({
      'notice.banner': { text: { ru: 'Осталось {days_left}' }, state: 'NOTICE', placement: 'banner' },
    })
  })

  it('drops messages when none are left', () => {
    const params = { ...DEFAULT_PARAMS, messages: { m: { text: { ru: 'x' } } } }
    const form = toForm(params)
    form.messages = []
    expect(toParams(form, params)).not.toHaveProperty('messages')
  })
})
