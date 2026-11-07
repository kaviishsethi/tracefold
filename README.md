# Tracefold

Review existing company material. Catch new risks while you work.

Tracefold is a new HACK1984 project with two experiences sharing one private scan engine:

- **Upload platform:** manually upload documents/code, or select planned connected sources, to check public exposure and potential risks.
- **MCP integration:** check workspace changes through a coding assistant, inspect findings, propose corrections and recheck them.

The strict-private deployment keeps the scan server and Ollama inside the trusted environment and uses a local-model MCP host. Uploading to a vendor server or returning private findings to a cloud-backed assistant changes that privacy boundary. GitHub is the first planned remote connector; Docs and sites follow later.

**Status: the shared engine (milestones 1–7 of the [shared engine plan](docs/SHARED_ENGINE_PLAN.md)) is implemented in [`server/`](server/README.md) and passes its offline test suite. The upload app and MCP adapter are not built yet; their contract is in [docs/ENGINE_API.md](docs/ENGINE_API.md). Model review has been run against a real local `qwen2.5:7b-instruct`; Exa/Tavily calls have not been run against live services yet.**

- [Shared engine implementation plan — build this first](docs/SHARED_ENGINE_PLAN.md)
- [Engine API handoff for the app and MCP adapter](docs/ENGINE_API.md)
- [Complete product, architecture, demo, and track plan](PLAN.md)
- [Original retrieval/privacy Excalidraw diagram (predates MCP)](docs/architecture.excalidraw) — download and open in [Excalidraw](https://excalidraw.com).
- [Original architecture preview](docs/architecture.svg)
- [Risk-review workflow informed by 0sec](research/0sec-risk-review.md)
- [Case-study research and CrowdSec fallback](research/case-study-research.json)

The [current two-experience architecture](PLAN.md#3-proposed-architecture) is in the plan. The original Excalidraw assets remain a reference for the retrieval boundary.

## The first demo

1. Upload a reference file through the platform and choose monitored public sources.
2. Refresh a source through Exa or Tavily and show computed matching passages with provenance.
3. Use the MCP-connected assistant to scan an unpublished code change and flag a separate synthetic sensitive-logging risk.
4. Review a suggested correction, apply it through the editor workflow, and recheck through MCP.
5. Show the same updated finding in the platform, the still-open public exposure, and the outbound ledger.

MCP is a first-class entry point. Automatic file watching and editor notifications are optional follow-ons; the first demo shows explicit assistant tool calls. Neither client surface is implemented yet; the engine they share is.

The result is **“matching content found publicly”** or **“no match in the sources checked,”** never a blanket assurance that a company is safe. A separate **Potential risks in your files** section provides preventive feedback even when no public match is found. These are review findings, not proof of a leak or a comprehensive security audit.

## Isolation from Spillway

This is a standalone repository and a new implementation plan. It does not copy Spillway's application, databases, credentials, Git history, or frozen interfaces. Only the case-study decision record is carried forward as small research metadata. Any future code reuse must be selected and reviewed explicitly.

Working name: Tracefold; no trademark or domain-availability claim is made.
