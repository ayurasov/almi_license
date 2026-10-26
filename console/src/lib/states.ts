// Presentation of the hourly state of a licence (E12-03): green while it works fully, amber while
// a term runs out, red when restricted or worse.
export type Severity = 'success' | 'warn' | 'danger' | 'secondary'

export function stateSeverity(state: string): Severity {
  if (state === 'ACTIVE' || state === 'TRIAL') return 'success'
  if (state === 'NOTICE' || state === 'GRACE') return 'warn'
  if (state === 'RESTRICTED' || state === 'BLOCKED' || state === 'REVOKED') return 'danger'
  return 'secondary'
}

/** States of the overview in their order: full work first, then those that need the operator. */
export const STATE_ORDER = ['ACTIVE', 'TRIAL', 'NOTICE', 'GRACE', 'RESTRICTED', 'BLOCKED', 'REVOKED', 'UNLICENSED']

/** States the operator should look at: a term ran out or functions are cut. */
export const ATTENTION_STATES = new Set(['GRACE', 'RESTRICTED', 'BLOCKED'])
