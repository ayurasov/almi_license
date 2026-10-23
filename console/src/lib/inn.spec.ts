import { describe, expect, it } from 'vitest'

import { innIsValid } from './inn'

describe('innIsValid', () => {
  it.each(['7707083893', '7736207543', '500100732259', '773370857141'])('accepts %s', (inn) => {
    expect(innIsValid(inn)).toBe(true)
  })

  it.each(['7707083894', '500100732258', '500100732249', '770708389', '77070838931', '', '77O7083893'])(
    'refuses %s',
    (inn) => {
      expect(innIsValid(inn)).toBe(false)
    },
  )
})
