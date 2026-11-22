# P2 / P3 — SaaS, Commercial & API Hardening

**Baseline:** `9357e06c381a4a52bd870d243e2bb2cf189c87d4`.
**Status:** Acceptance scope; payment/email/webhook production readiness is not claimed.

## Identity, tenancy and permissions

- Audit every identifier-bearing route, cache key, background job, report, conversation, evidence query and export for organization/farm/field scope.
- Verify owner/admin/member permission matrices on both current and legacy routes.
- Confirm email verification is mandatory outside dev mode and refresh/session revocation works with persisted database state.
- Test organization switching; billing, reports, analytics and developer screens must use the explicitly selected organization, not the first membership.

## Entitlements and billing

- Enforce Free/no-subscription, trial, paid, downgrade, expired and cancelled entitlements consistently at API boundaries.
- A disabled API entitlement or zero rate limit must fail closed; never substitute a positive default.
- Keep sandbox billing clearly labelled; production must fail closed until a real payment provider, signature validation, replay protection, reconciliation and refund/dispute semantics are implemented.
- Verify invoice amount/currency/customer/organization binding and idempotent webhook processing.

## Notifications, analytics and developer API

- Test severity filtering, pagination, unread counts, deduplication and delivery retries.
- Verify analytics filters and aggregation boundaries by organization, field and time; distinguish observed metrics from derived estimates.
- Validate API key issuance, scope, expiry, rotation, revocation, quotas, rate limits and audit trail.
- Harden outbound webhooks against DNS rebinding, redirects, private/link-local destinations, secret leakage and duplicate delivery; encrypt or externalize signing secrets.

## Acceptance criteria

- Route-level integration tests prove tenant and entitlement boundaries for both allowed and denied cases.
- Database-backed tests cover billing lifecycle and webhook idempotency.
- No production payment, email or webhook feature is represented as live until credentials and external delivery evidence exist.
- All commercial actions expose accessible loading, success, error and retry states.
