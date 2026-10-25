import { describe, expect, it } from 'vitest'

import { formErrors } from './customerSchema'

const valid = { name: 'ООО «Ромашка»', inn: '7707083893', external_id: '', status: 'active' }

describe('customer form', () => {
  it('accepts a valid customer and an empty INN', () => {
    expect(formErrors(valid)).toEqual({})
    expect(formErrors({ ...valid, inn: '' })).toEqual({})
  })

  it('names the fields with i18n keys', () => {
    expect(formErrors({ ...valid, name: '  ', inn: '7707083894' })).toEqual({
      name: ['customers.errors.nameRequired'],
      inn: ['customers.errors.innInvalid'],
    })
  })
})
