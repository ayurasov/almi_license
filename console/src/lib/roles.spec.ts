import { describe, expect, it } from 'vitest'

import { canChange, canOpen } from './roles'

describe('roles', () => {
  it('a customer viewer opens licences, statistics and the journal only', () => {
    expect(['licenses', 'license', 'stats', 'audit'].every((s) => canOpen('customer_viewer', s))).toBe(true)
    expect(['customers', 'import', 'users', 'servers', 'catalog'].some((s) => canOpen('customer_viewer', s))).toBe(false)
    expect(canChange('customer_viewer')).toBe(false)
  })

  it('users are for administrators', () => {
    expect(canOpen('operator', 'users')).toBe(false)
    expect(canOpen('admin', 'users')).toBe(true)
    expect(canOpen('operator', 'customers')).toBe(true)
    expect(canChange('operator')).toBe(true)
  })
})
