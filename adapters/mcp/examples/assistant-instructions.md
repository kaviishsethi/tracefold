## Tracefold checks

This workspace is connected to Tracefold through the `tracefold` MCP server.

- After you edit files, and before you report work as complete, call `scan_changes` (default: Git changes against
  `HEAD`, including untracked files). If `done` is false, call `get_scan` until it is, then `get_findings` with
  that `scan_id`.
- Report the two sections separately: **Potential risks in your files** (`local_risk`) and **Public exposure**
  (`public_exposure`). Quote `coverage_notes` for empty or incomplete sections.
- Use `explain_finding` for evidence, conditions, uncertainty and the stored suggested fix. Propose a correction,
  and apply it only through the normal editing workflow, with the user's approval.
- After a fix, call `recheck_fix` with the finding ID and report its `outcome` as it is given.
- Never describe a file as "safe" or a finding as "fixed". `completed` means the requested checks finished within
  their stated coverage. `not_detected_in_checked_version` applies only to the checked version. A local recheck
  never closes a public-exposure finding.
- Never read, print or test a detected credential.
