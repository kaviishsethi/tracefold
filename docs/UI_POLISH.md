# App polish

Approved scope: preserve the current palette, Geist typeface, navigation, features and section order; apply a craft pass across the app. Marketing and landing-page styling are excluded. This is not the previously rejected graphite/cyan redesign.

## Direction

- Product: security teams configure public searches and review matching evidence.
- Character: exact, practical, restrained.
- World: source review and search configuration, within the existing visual identity.
- Moments: actual queries and source passages carry the content; no decorative images.
- Signature: queries remain paired with their provider and scope.

## Nine passes

1. **Spacing:** consistent form spacing, 20px panel headers, 16px finding rows and a clearer gap between Discovery's working column and guidance.
2. **Color:** existing surfaces and accent retained. Muted metadata raised to #949c99 for readability. Dark panel shadows removed; approval counts are quiet text.
3. **Icons:** existing Lucide set retained. Removed the green check beside the disclosure explanation, which was not a success result.
4. **Copy:** readable pack/search names replace API identifiers in display labels. Experimental status remains visible; repeated benchmark badges are removed from choices. Exact query strings and API values are unchanged.
5. **Type:** consistent 28px desktop / 26px mobile app headings, 14px panel headings, and metadata at least 12px where smaller utilities existed. Geist retained.
6. **Layout:** same sections and order. Discovery's supporting column is 280px, leaving more width for configuration. Phone navigation wraps without overflow; finding timestamps get their own line.
7. **Details:** pack choices no longer each need an outlined card; selected choices keep their border. Larger controls, visible focus, keyboard-accessible file selection, and a focusable horizontally scrolling query table. Approval URLs wrap inside their cards.
8. **Visuals:** no images generated or decorative objects introduced. Real queries, provider names and source evidence remain the content focus.
9. **Motion:** existing purposeful transitions retained; app-scoped reduced-motion support disables animations and transitions.

## Verification

TypeScript and targeted ESLint pass; git diff whitespace check passes. Inspected Discovery on desktop and phone, including the expanded query preview and search chooser. Inspected mobile findings, evidence, approvals and scan screens. Confirmed the approval URL wrapping fix. No plan was created, no scan submitted and no approval sent during UI verification.

App styles are scoped to `.app-polish`, which the public-page branch of the shell does not render. Shared UI changes only add styling hooks. Landing files and global theme tokens were not edited.

Based on **unslop by Damir Sokolovsky (@heydamir)**, licensed CC BY 4.0: https://heydamir.design/unslop.
