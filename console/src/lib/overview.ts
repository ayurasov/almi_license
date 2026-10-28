// The overview screen: what of the statistics needs the operator (console/docs/design.md).
import { ATTENTION_STATES, STATE_ORDER } from '@/lib/states'

const DAY = 24 * 60 * 60 * 1000

export interface ExpiringRow {
  license_id: string
  customer_name: string
  product: string
  valid_until: string | null
  status: string
}

/** Active licences whose term ends within `days` from `now`, the nearest first. */
export function expiring<T extends ExpiringRow>(rows: T[], now: Date, days: number): T[] {
  const until = now.getTime() + days * DAY
  return rows
    .filter((row) => row.status === 'active' && row.valid_until !== null)
    .filter((row) => {
      const end = Date.parse(row.valid_until ?? '')
      return end >= now.getTime() && end <= until
    })
    .sort((a, b) => Date.parse(a.valid_until ?? '') - Date.parse(b.valid_until ?? ''))
}

/** Whole days left until `iso`, never below zero. */
export function daysLeft(iso: string, now: Date): number {
  return Math.max(0, Math.ceil((Date.parse(iso) - now.getTime()) / DAY))
}

/** Counts of states in the order of the overview, without the empty ones. */
export function statesInOrder(byState: Record<string, number>): { state: string; count: number }[] {
  const count = (state: string): number => byState[state] ?? 0
  const known = STATE_ORDER.filter((state) => count(state) > 0)
  const other = Object.keys(byState).filter((state) => !STATE_ORDER.includes(state) && count(state) > 0)
  return [...known, ...other].map((state) => ({ state, count: count(state) }))
}

/** Licences that need the operator: grace, restricted or blocked. */
export function needAttention(byState: Record<string, number>): number {
  return Object.entries(byState).reduce((sum, [state, count]) => sum + (ATTENTION_STATES.has(state) ? count : 0), 0)
}

/** Share of the seats taken, in per cent, for the progress bar. */
export function seatsTaken(active: number, limit: number): number {
  return limit > 0 ? Math.min(100, Math.round((active / limit) * 100)) : 0
}
