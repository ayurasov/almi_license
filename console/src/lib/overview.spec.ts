import { describe, expect, it } from 'vitest'

import { daysLeft, expiring, needAttention, seatsTaken, statesInOrder } from './overview'
import { stateSeverity } from './states'

const now = new Date('2026-10-26T12:00:00Z')

function row(id: string, validUntil: string | null, status = 'active') {
  return { license_id: id, customer_name: id, product: 'p', valid_until: validUntil, status }
}

describe('overview', () => {
  it('lists active licences ending within the period, the nearest first', () => {
    const rows = [
      row('later', '2026-11-20T20:59:59Z'),
      row('soon', '2026-10-28T20:59:59Z'),
      row('past', '2026-10-20T20:59:59Z'),
      row('far', '2027-01-01T00:00:00Z'),
      row('perpetual', null),
      row('suspended', '2026-10-30T00:00:00Z', 'suspended'),
    ]
    expect(expiring(rows, now, 30).map((r) => r.license_id)).toEqual(['soon', 'later'])
  })

  it('counts whole days left and never goes below zero', () => {
    expect(daysLeft('2026-10-28T20:59:59Z', now)).toBe(3)
    expect(daysLeft('2026-10-01T00:00:00Z', now)).toBe(0)
  })

  it('orders the states and counts those that need the operator', () => {
    const byState = { BLOCKED: 1, ACTIVE: 5, GRACE: 2, CUSTOM: 1, NOTICE: 0 }
    expect(statesInOrder(byState)).toEqual([
      { state: 'ACTIVE', count: 5 },
      { state: 'GRACE', count: 2 },
      { state: 'BLOCKED', count: 1 },
      { state: 'CUSTOM', count: 1 },
    ])
    expect(needAttention(byState)).toBe(3)
  })

  it('gives the share of seats taken', () => {
    expect(seatsTaken(3, 4)).toBe(75)
    expect(seatsTaken(5, 4)).toBe(100)
    expect(seatsTaken(0, 0)).toBe(0)
  })

  it('colours the states', () => {
    expect(stateSeverity('ACTIVE')).toBe('success')
    expect(stateSeverity('GRACE')).toBe('warn')
    expect(stateSeverity('BLOCKED')).toBe('danger')
    expect(stateSeverity('UNLICENSED')).toBe('secondary')
  })
})
