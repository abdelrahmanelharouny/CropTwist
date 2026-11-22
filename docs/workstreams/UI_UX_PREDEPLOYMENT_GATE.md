# UI/UX — Mandatory Pre-deployment Gate

**Baseline:** `9357e06c381a4a52bd870d243e2bb2cf189c87d4`.
**Status:** Gate definition only. This branch is intentionally clean from current `main`; the old redesign branch is not merged wholesale.

## Product direction

CropTwist should feel like a professional agricultural decision-intelligence workspace: information-dense but calm, evidence-first, distinctive, responsive and trustworthy. The current dark forest/mint token system is a starting point, not proof that every screen is polished. Avoid generic AI-dashboard patterns, decorative gradients, excessive cards, fake metrics and animation that obscures data.

## UX audit scope

Review all nine destinations and every sub-page: Overview; Farms & Fields; Data Hub; Crop Intelligence; Map & Satellite; Decision Center; AI Copilot; Reports & Analytics; Workspace & Settings. Inspect desktop and mobile, English and Arabic RTL, empty/loading/error/partial/stale states, and real-data versus synthetic-data disclosures.

## Design requirements

- Establish clear page hierarchy, consistent spacing/type scale, compact but readable data tables and purposeful density.
- Make navigation, selected farm/field context, breadcrumbs and active state unambiguous; preserve canonical URL, Back/Forward and deep-link behavior.
- Use semantic status colors and accessible contrast; do not use green for every state.
- Ensure charts/maps have legends, units, time ranges, empty states, keyboard-accessible controls and readable mobile fallbacks.
- Respect RTL logically, including directional icons, alignment, drawers, table overflow and map controls.
- Motion must be purposeful: short transitions for navigation/feedback, reduced-motion support, no continuous decorative motion, no layout shift.
- Every action needs visible pending/success/error/retry feedback; disabled controls need a reason.
- Preserve all API, query, tenant, evidence and agronomic contracts. UI must not invent scores, observations, availability or saved/approved plans.

## Browser and accessibility QA

1. Run authenticated browser journeys on disposable PostGIS data; block external traffic and use synthetic fixtures only where explicitly labelled.
2. Capture 1440px, 1024px, 390px and 360px for English and Arabic.
3. Verify all primary destinations, sub-pages, deep links, navigation history, mobile sheet, keyboard-only flows and focus return.
4. Inject 401/403/404/409/422/429/500/503, timeout, empty, partial and stale responses; wait through query retries before asserting.
5. Validate forms, uploads, maps, charts, reports, billing, notifications and developer API interactions.
6. Check WCAG 2.2 AA contrast, visible focus, accessible names, 44px touch targets, reduced motion and screen-reader landmarks.
7. Compare screenshots against approved design references and record actionable defects; do not call a static screenshot matrix a full interaction test.

## Hard release gate

UI/UX review, responsive/RTL browser journeys, accessibility checks, chart/map rendering and error/retry states must pass **before deployment**. No production deploy while this gate is open.
