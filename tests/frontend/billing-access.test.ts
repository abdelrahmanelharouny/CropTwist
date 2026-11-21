import { describe, expect, test } from 'bun:test'
import { canManageBilling } from '../../src/lib/billing-access'

describe('canManageBilling', () => {
  test('allows only owner and org_admin roles', () => {
    expect(canManageBilling('owner')).toBe(true)
    expect(canManageBilling('org_admin')).toBe(true)
    expect(canManageBilling('member')).toBe(false)
    expect(canManageBilling('viewer')).toBe(false)
    expect(canManageBilling(null)).toBe(false)
    expect(canManageBilling(undefined)).toBe(false)
  })
})
