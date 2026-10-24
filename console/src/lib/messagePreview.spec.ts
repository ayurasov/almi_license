import { describe, expect, it } from 'vitest'

import { preview, type Sample, unknownSubstitutions } from './messagePreview'

const sample: Sample = {
  days_left: '7 дн.',
  valid_until: '31.10.2027',
  customer: 'ООО «Ромашка»',
  used: '42',
  limit: '50',
  product: 'АльтерОфис',
  support_contact: 'support@example.org',
}

describe('message preview', () => {
  it('fills known substitutions and keeps unknown ones visible', () => {
    expect(preview('{product}: осталось {days_left} до {valid_until}, {used}/{limit}', sample)).toBe(
      'АльтерОфис: осталось 7 дн. до 31.10.2027, 42/50',
    )
    expect(preview('Срок {days}', sample)).toBe('Срок {days}')
  })

  it('lists unknown substitutions once, sorted', () => {
    expect(unknownSubstitutions('{days} {x} {days} {customer}')).toEqual(['days', 'x'])
    expect(unknownSubstitutions('без подстановок')).toEqual([])
  })
})
