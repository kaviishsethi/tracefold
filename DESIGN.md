---
name: Tracefold
description: An open technical surface for reviewing evidence and code risks.
colors:
  paper: "#111619"
  ink: "#e1e8eb"
  muted: "#98a6ae"
  line: "#2b363c"
  accent: "#81c8d5"
  highlight: "#25434a"
  green: "#98c8a1"
  warning: "#d6b77c"
typography:
  heading:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "28px"
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: "-.025em"
  body:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "DM Sans, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
  source:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.9
rounded:
  control: "4px"
spacing:
  small: "8px"
  control: "12px"
  medium: "16px"
  section: "24px"
  column: "32px"
  page: "48px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  review-field:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px"
  navigation:
    textColor: "{colors.muted}"
  source-match:
    backgroundColor: "{colors.highlight}"
    textColor: "#c5eaf0"
---

# Design System: Tracefold

## Overview

**Creative North Star: "The Technical Review Surface"**

Graphite, cyan, and source typography put files and evidence first. Flat top navigation and ruled findings provide structure without boxed panels. Short labels and native disclosures keep supporting explanation available without dominating the task.

The user requested a minimal technical theme and rejected the earlier boxed, verbose design and subsequent warm serif treatment. This records the current implementation proposal, not final screen approval. It remains a static interactive prototype with sample data and no backend connection.

**Key Characteristics:**
- Open ruled layout, no sidebar or card grid.
- Sans-serif controls and monospace source evidence.
- Cyan matching passages on graphite.
- Concise task copy with supporting details on demand.

## Colors

Graphite (`paper`) is the continuous canvas; pale ink and cool gray (`muted`) establish hierarchy. Cyan (`accent`) marks primary actions, focus, and the match key; deep teal (`highlight`) supports source matches. Amber (`warning`) identifies open observations and coverage gaps. Green marks bounded recheck outcomes. Thin blue-gray rules (`line`) divide content. Frontmatter owns exact values.

## Typography

DM Sans supplies headings, controls, and metadata. System monospace supplies source passages, line numbers, file labels, and diffs. Newsreader remains a legacy asset/token but is overridden in the current source view; it is not part of this direction. Page headings are 28px, falling to 26px on phones. Source text is 14px/1.9, falling to 13px/1.9. Metadata stays at least 12px.

## Layout

A 64px top bar holds brand, workspace, navigation, and demo label. Main content is capped at 1216px with 48px side padding and 36px top padding. Findings are open horizontal rows; expanded evidence is indented 132px on wide screens. Two source columns share a thin divider and 32px gap. Scan setup is a single column capped at 680px, with checks/privacy behind a disclosure.

At 1000px, the workspace label disappears, page side padding becomes 32px, and evidence loses its indent. At 600px, navigation wraps below the brand, page side padding becomes 20px, and sources stack private before public with a horizontal rule and 24px gap. Tables and code scroll when needed.

## Elevation & Depth

No shadows, floating cards, or nested panels. Rules, spacing, and type provide hierarchy on one continuous canvas.

## Shapes

Controls and fields use restrained 4px corners. Findings and source areas are unboxed. Small circular status dots always accompany written labels.

## Components

- **Buttons:** cyan primary; transparent secondary. Minimum 44px height, 10px 16px padding. Hover uses pale cyan or dark slate; background changes take 150ms. Keyboard focus uses a 2px cyan outline with 4px offset. Reduced motion disables transitions.
- **Fields:** transparent background, muted border, 12px padding. Upload is an open ruled row with a keyboard-visible outline; file removal has a 44px target.
- **Navigation:** quiet horizontal links with an ink underline for the current page. Evidence tabs support Arrow/Home/End keys.
- **Source comparison:** monospace line-number gutters, labeled private/public sources, teal filled passage matches. Match details use native disclosure.
- **Findings and recheck:** ruled rows, textual status, open code diff with plus/minus markers. Check history folds away; public-match status remains independently visible.

## Do's and Don'ts

### Do:
- **Do** keep source names, line numbers, and matching passages together.
- **Do** use short action labels and disclosures for secondary explanation.
- **Do** preserve 12px minimum metadata and 44px control targets.
- **Do** distinguish sample operations, coverage gaps, and separate public observations.

### Don't:
- **Don't** restore warm paper, serif evidence, sidebar navigation, or boxed cards.
- **Don't** use decorative summaries or repeated explanatory slogans.
- **Don't** imply a local recheck resolves a public match.
