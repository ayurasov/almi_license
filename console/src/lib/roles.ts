// What a role sees in the console; the server checks the same rights (E07-08, E07-09).
const VIEWER_SCREENS = new Set(['licenses', 'license', 'stats', 'audit'])

export type Role = 'operator' | 'admin' | 'customer_viewer'

export function canOpen(role: Role | undefined, screen: string): boolean {
  if (role === 'customer_viewer') return VIEWER_SCREENS.has(screen)
  if (screen === 'users') return role === 'admin'
  return role !== undefined
}

// A customer viewer only reads: no actions on licences, keys or activations.
export function canChange(role: Role | undefined): boolean {
  return role === 'operator' || role === 'admin'
}
