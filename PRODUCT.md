# Tracefold

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
User-approved interactive HTML/CSS mockups, with plain JavaScript for prototype behavior. The planned application uses the existing Python engine; Next.js remains a future implementation choice.

## Users
- **Buyer:** the head of security (CISO or head of information security) at companies in industries such as financial services, healthcare, government and retail.
- **Users who approve:** senior security leaders below the CISO (VP, director or manager of security) who have authority to approve takedown requests and key shut-offs on the company's behalf.
- **Users who scan:** security engineers and developers, including coding assistants over MCP. They run scans and fix code but can't approve takedowns or key changes.
- Today the approve permission belongs to the web app's token and is never given to coding assistants; per-person roles would come with single sign-on.
- The company's industry decides which regulated data the local checks look for.

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
