/** Billing administration is restricted to the organization owner/admin. */
export function canManageBilling(role: string | null | undefined): boolean {
  return role === 'owner' || role === 'org_admin'
}
