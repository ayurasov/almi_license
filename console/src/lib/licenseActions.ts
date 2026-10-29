// Actions of the licence card. A local server gets rights in the package of the central server:
// it may suspend or revoke, but not create, renew, change terms, resume, lift a block or transfer
// (decision of 29.10.2026; the server refuses them too).
import type { LicenseAction } from '@/stores/licenses'

export function licenseActions(status: string | undefined, changes: boolean, local: boolean): LicenseAction[] {
  if (status === 'revoked' || !changes) return []
  if (local) return status === 'suspended' ? ['revoke'] : ['suspend', 'revoke']
  return ['renew', status === 'suspended' ? 'resume' : 'suspend', 'liftBlock', 'settings', 'transfer', 'revoke']
}
