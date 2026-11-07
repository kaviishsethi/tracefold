# 0sec reference: preventive risk review

Reviewed November 7, 2026 at commit `7a7000bbe4efc5387d64869ba6264ae0aa64af24`. This is a source/documentation review, not an installation, benchmark, or validation of 0sec's effectiveness. No upstream code has been copied or executed.

## What is useful

- **Discovery and verification are distinct.** Their blind-verification documentation describes fresh verifier contexts and source-specific review gates. It explicitly distinguishes model assessments from executable reproduction. A second model pass can still share biases and does not prove exploitability. [Verification documentation](https://github.com/0sec-labs/0/blob/7a7000bbe4efc5387d64869ba6264ae0aa64af24/docs/src/content/docs/blind-verification.md).
- **Validate findings before persistence.** Their draft validator checks identifier formats and bounds evidence paths to the workspace, including symlink escapes. This is structural validation: a syntactically valid CVE need not exist, and an allowed evidence path need not contain supporting evidence. The implementation permits some nonexistent artifact paths, so Tracefold must additionally require existing imported source locations. [Validator source](https://github.com/0sec-labs/0/blob/7a7000bbe4efc5387d64869ba6264ae0aa64af24/packages/core/src/agent/finding-validator.ts).
- **Accept structured leads.** Their external-seed parser records file, line range, snippet, source and optional claim/metadata. This is a useful boundary for deterministic checks feeding model review. Their parser is permissive; our schema must additionally validate line bounds against the imported snapshot. [Seed parser](https://github.com/0sec-labs/0/blob/7a7000bbe4efc5387d64869ba6264ae0aa64af24/packages/core/src/seed-findings.ts).
- **Group and prioritize without inventing verification.** Optional postprocessing deduplicates findings and ranks canonical entries; failures fall back without dropping findings. These features are flag-gated, not universally enabled defaults. [Postprocessing source](https://github.com/0sec-labs/0/blob/7a7000bbe4efc5387d64869ba6264ae0aa64af24/packages/core/src/agentic/finding-postprocess.ts).
- **Keep advisory checks separate from vulnerability verdicts.** Their project checks can report pass, issue or unknown. Their source review may use networking and tooling; fix workflows require stronger executable evidence and regression checks. These capabilities are not equivalent to Tracefold's no-egress, read-only MVP. [Workflow documentation](https://github.com/0sec-labs/0/blob/7a7000bbe4efc5387d64869ba6264ae0aa64af24/docs/src/content/docs/scan-workflows.md).

## Proposed Tracefold implementation

Use one local Ollama instance with separate bounded prompts; a fresh prompt is a review step, not an independent expert or runtime verifier.

1. **Inventory and scope.** Parse supported files once, retain stable document IDs, offsets and content hashes, and show skipped/truncated files. Separate document checks from code/config checks.
2. **Generate leads.** Small local rules identify apparent secrets, sensitive logging patterns and explicit risky configuration. Route bounded source context to focused model checks. A pattern hit starts as a lead, not a confirmed exposure. Documents receive checks for sensitive content and sharing/redaction conditions; they do not receive generic code vulnerability labels.
3. **Investigate context.** Ollama explains the exact concern and conditions using supplied source locations. For code, request the input/source, sensitive operation or destination, relevant guard, and missing context. For documents, identify the sensitive category and the sharing scenario that creates risk. Unsupported repository-wide claims are rejected.
4. **Validate evidence.** Enforce the output schema, imported-file membership, real location bounds and snippet agreement with the immutable local input. Reject outside-workspace paths, fabricated locations and secret-bearing output. Structural validity does not establish semantic correctness.
5. **Challenge each candidate.** A fresh local prompt looks for counterevidence: masking before logging, a guard, test-only code, a placeholder value, or an unknown deployment setting. Record supported, dismissed with reason, or inconclusive. Never promote a model verdict to runtime-confirmed. Preserve rule evidence if model review fails.
6. **Present and repair.** Group duplicates using file/location/category first. Rank by evidence and plausible impact, with rationale. Provide a suggested edit/redaction and a verification step. After the user changes the file, rerun the same check and report whether that specific pattern remains; do not equate disappearance with comprehensive remediation.

Suggested finding record: `id`, `input_snapshot`, `check_id`, `check_version`, `file_id`, `location`, `evidence_refs`, `origin` (rule/model), `claim`, `conditions`, `counterevidence`, `review_status`, `severity_rationale`, `suggested_fix`, `recheck`, `model_id`, `prompt_version`. Keep public-exposure state in a separate record. Do not persist raw sensitive snippets by default.

Initial budget: at most 10 candidate leads per scan, one discovery pass per bounded chunk, one skeptical pass per candidate, and one schema-repair retry. Cap total model requests at 25 and total submitted context across requests at 40,000 tokens, using the selected model's tokenizer; each request must also fit its context window. Enforce the existing five-minute scan deadline with cancellation, expose unreviewed leads and truncation, and tune these proposed limits only after a small measured timing/RAM pilot. Reuse the existing local input snapshot; do not create per-finding repo copies.

MVP check set: apparent embedded secrets, sensitive logging, explicit unsafe sharing/access configuration, and document content needing redaction for a stated audience. Broader injection/authentication analysis is later work after basic precision is measured. No runtime exploitation, dependency installation, autonomous shell, arbitrary browsing, or automatic patches are introduced by this plan.

## Demonstration and evaluation

Use a synthetic unpublished file with a visible sensitive-logging issue. Show no public match, then the source-backed potential-risk finding. Import a corrected version and show the same check no longer flags that pattern. Include a benign lookalike and an incomplete-context case; the latter should remain inconclusive. Use fake secret-like values only.

Measure false alarms, missed labeled issues, evidence-location validity, correction/recheck behavior, budget exhaustion and model-unavailable behavior separately from leak-match accuracy. Evaluate the actual Ollama model: 0sec's architecture alone supplies no evidence that a small local model achieves equivalent results.

## Decision

Borrow the workflow and evidence discipline, not the entire harness. Keep Tracefold's focus on public exposure plus preventive data-leak risks. The proposed stages remain unimplemented. An optional future harness integration would require a separate review of model routing, tool permissions, outbound traffic, execution isolation, resource costs and licensing for the exact files reused.
