# Tracefold landing-page art

Ten teal adaptations generated with the built-in image generation tool using the existing local 0.security previews as edit references. These preserve the cloudscape and glass subjects, composition, and texture while adapting the palette; they are reference-based edits, not independently created source compositions.

Palette: muted teal `#4fb8a6`, deep teal `#1f6f66`, charcoal `#0a0c0c`, pale mint-white highlights. PNG results are encoded as WebP (quality 88) for the page. Assets live in `public/art/`; `lib/landing-art.ts` is the shared path manifest. Existing layout, crops, and overlays are retained.

## Asset inventory

| Asset | Placement | Reference |
| --- | --- | --- |
| `hero-clouds.webp` | Hero; first carousel card | `soft-hero.webp` |
| `open-sky.webp` | Evidence carousel card; workflow step 02 | `cloud-field.webp` |
| `dusk-clouds.webp` | Workflow step 01; security-team band | `cloud-dusk.webp` |
| `halftone-sky.webp` | Potential-risk carousel card; coding-assistant integration | `workflow-dusk-soft-halftone-v3.webp` |
| `connected-clouds.webp` | Approval carousel card | `dependency-security-20261020.webp` |
| `stippled-clouds.webp` | Ledger carousel card; closing call to action | `pointillist-hero.webp` |
| `onboarding-sky.webp` | Setup band | `onboarding-clouds.webp` |
| `review-clouds.webp` | Workflow step 03 | `workflow-verification-20261030.webp` |
| `recheck-clouds.webp` | Workflow step 04 | `workflow-memory-20261030.webp` |
| `ledger-glass.webp` | Outbound-request ledger panel | `comparison-open-20261026.webp` |

## Generation prompts

### Hero

Edit the supplied cloud photograph for the Tracefold landing page. This is a restrained professional color-grade adaptation. Preserve the natural cloud photography, exact cloud forms, framing, softness, contrast, realistic atmospheric depth, and existing dark lower area for text. Replace orange sunset light with soft pale mint / muted teal light (#4fb8a6); replace warm gray shadows with charcoal and very dark desaturated teal (#0a0c0c, #18302e). Highlights may approach neutral off-white. The bright upper sky should remain softly luminous but be desaturated sea-glass rather than orange. Keep it photographic and understated, like the supplied image, with no added objects, shapes, ribbons, neon effects, stars, symbols, typography or illustration. Change only the palette. Output landscape with original 16:9 composition.

### Shared instructions for the remaining assets

Make a restrained professional color-grade edit of this supplied reference for the Tracefold website. Preserve its subject, composition, realism, relative luminance, fine texture and clean premium quality. Change the color palette to Tracefold: muted teal #4fb8a6, deep teal #1f6f66, charcoal #0a0c0c, and pale mint-white highlights. Avoid saturated green, cyan, neon, orange, purple or warm sunset colors. Do not add any abstract ribbons, rings, ornaments, symbols, typography, logos, borders or UI. 

### open-sky.webp

Keep the open sky framed by clouds, fine curved trail lines, pale airy center and detailed cloud edges. Grade blue/purple sky to desaturated teal; orange rims to pale mint. Landscape 16:9.

### dusk-clouds.webp

Keep the cloud bank rising along the lower left, open upper-right sky and single delicate curved light trail from upper left. Grade blues to deep teal, sunset rims and trail to pale sea-glass. Landscape 16:9.

### halftone-sky.webp

Keep the diagonal wispy cloud bands, subtle halftone print texture and dark lower half. Sunset streaks become muted teal and pale mint against charcoal teal-gray sky. Square composition.

### connected-clouds.webp

Keep the rectilinear dark blocks nestled in realistic clouds, their thin connections, wide composition and dark left side. Sunset light becomes pale mint, clouds charcoal teal; connections softly teal, never neon. Preserve delicate lighting and material realism. Very wide 3:1 composition.

### stippled-clouds.webp

Keep the dark open central sky, cloud banks, distant block silhouettes lower-left, fine stippled grain and detailed pointillist texture. Orange cloud rims become restrained muted teal/mint dots, charcoal-teal shadows. Landscape 16:9.

### onboarding-sky.webp

Keep the generous open sky in the upper center framed by low banks of clouds on both sides and along the bottom. Orange light becomes pale mint, blue sky desaturated teal, shadows dark teal-gray. Preserve soft natural clouds with their precise delicate texture, no additional objects. Landscape 3:2.

### review-clouds.webp

Keep the detailed cloud banks along left and bottom, open center, diagonal natural rays of light entering from upper right. Orange sunlit areas become pale neutral mint-white, blue shadows deep teal and charcoal, realistic soft sky. Landscape 3:2.

### recheck-clouds.webp

Keep the upper-left light source, textured cloud bank on the left and bottom, and open upper-right sky. Orange becomes pale mint, blue/purple sky desaturated teal, lower clouds deep charcoal-teal. Preserve soft photographic light. Landscape 3:2.

### ledger-glass.webp

Keep the exact clean cropped transparent rectangular glass block on the right, its realistic sharp straight edges, refraction, soft reflections on the dark floor and expansive dark left side. Replace orange refractions and reflections with muted teal #4fb8a6 and pale mint, blue environmental illumination with desaturated dark teal, background nearly black. No new shapes or extra details. Portrait 2:3.

