# Tracefold

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
User-approved interactive HTML/CSS mockups, with plain JavaScript for prototype behavior. The planned application uses the existing Python engine; Next.js remains a future implementation choice.

## Users
Security engineers at companies, in industries such as financial services, healthcare, government and retail, reviewing existing company material, and developers checking workspace changes through an MCP-connected assistant. The company's industry decides which regulated data the local checks look for.

## Product Purpose
Compare private material against explicitly selected public sources; inspect matching passages, preventive risks, coverage, and evidence-backed next steps.

## Operating Context
Two first-class entry points share one engine and versioned findings: file upload and explicit assistant checks. The approved mockup scope is scan setup, public evidence review, and local-risk fix/recheck review.

## Capabilities and Constraints
The shared engine exists; the upload app and MCP adapter are not implemented. Mockups use labeled synthetic examples, not live findings. Public exposure and potential risks in files are separate. No whole-web coverage, blanket safety score, automatic watching, or confirmed privacy claim. Rechecking local code does not close a public exposure. GitHub, Docs, and sites connectors are planned. Scanners are read-only; corrections are applied through the developer's editor.

## Evidence on Hand
PLAN.md, README.md, docs/ENGINE_API.md, server/fixtures/private/roadmap.md and the engine contract. Use the Northwind Relay synthetic fixture as illustrative content.

## Product Principles
- Evidence and coverage stay together.
- Unknown and failed checks remain visible.
- Both entry points refer to the same findings and input versions.
- Show what leaves the environment without promising nothing leaves.
- Use short task language and accessible working controls.
