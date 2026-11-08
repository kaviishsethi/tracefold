# Tracefold interactive design study

Run from this folder with `python3 -m http.server 4318 --bind 127.0.0.1`, then open http://127.0.0.1:4318.

Routes: `#evidence`, `#scan`, `#recheck`, `#activity`. This is a self-contained HTML/CSS/JavaScript prototype, not the upload application. All content and operations are illustrative. File selection reads names only; no private content is read or sent. Review notes and recheck state last only for the current page session. Reload resets them.

Try selecting Coverage, adding a review note, removing all files to see the empty state, submitting without files to see validation, or running the simulated fix/recheck and returning to Findings. Public exposure stays open after a local recheck.

The Northwind Relay roadmap derives from the synthetic fixture in `server/fixtures/private/roadmap.md`. Public source text, times, IDs, code and observations are illustrative. The completed-scan preview reflects selected options, then explicitly opens the fixed example; it never pretends to scan selected files.

## Direction

Current proposal: a minimal technical review surface in graphite and cyan. Flat top navigation, open ruled findings, and line-numbered monospace passages replace the rejected boxed study and warm serif revision. Setup uses one concise column with checks/privacy disclosed on demand. The user requested the technical theme and no boxes; these exact screens remain a proposal.

References: [Linear UI redesign](https://linear.app/now/how-we-redesigned-the-linear-ui) informs restrained hierarchy/navigation; [GitHub docked reviews](https://github.blog/changelog/2026-03-19-view-code-and-comments-side-by-side-in-pull-request-files-changed-page/) informs source-first comparison. The first study is preserved in `.impeccable/rejected-v1.zip`.

## Assets and credits

DM Sans is locally hosted. Newsreader remains a legacy local asset, but current source evidence uses system monospace. Icons are selected Lucide SVGs, with license in `assets/lucide-LICENSE`. Sources: https://fonts.google.com/specimen/DM+Sans, https://fonts.google.com/specimen/Newsreader, https://lucide.dev/guide/ and https://github.com/lucide-icons/lucide. No remote requests are made by the running prototype.

Design review follows Impeccable and Unslop. Unslop by Damir Sokolovsky (https://x.com/heydamir), CC BY 4.0; no skill source is redistributed.

Resource budget: static assets and source under 2 MB; at most 12 QA screenshots under 10 MB, kept in `.impeccable/review/` and excluded from Git. No dependency installation, database copy, backend scan, or model invocation is needed.

## Verification

Earlier browser verification applies to the superseded study; it does not establish visual approval or QA for this revision. Recheck desktop, the actual app preview width, and phone after implementation changes. Exercise tabs, review editing, file selection/validation, sample completion, and the separate public observation after recheck. Screenshots are disposable local QA artifacts, excluded from Git.
