import { describe, expect, it } from 'vitest'

import { licenseActions } from './licenseActions'

describe('licenseActions', () => {
  it('gives every action on the central server', () => {
    expect(licenseActions('active', true, false)).toEqual([
      'renew',
      'suspend',
      'liftBlock',
      'settings',
      'transfer',
      'revoke',
    ])
    expect(licenseActions('suspended', true, false)).toContain('resume')
  })

  it('keeps only suspend and revoke on a local server: rights come in the package', () => {
    expect(licenseActions('active', true, true)).toEqual(['suspend', 'revoke'])
    expect(licenseActions('suspended', true, true)).toEqual(['revoke'])
  })

  it('gives nothing for a revoked licence or a viewer', () => {
    expect(licenseActions('revoked', true, false)).toEqual([])
    expect(licenseActions('active', false, false)).toEqual([])
  })
})
