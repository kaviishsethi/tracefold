# Tracefold demo video: plan, shot list and voiceover

Target length **about 2:45**. The rules say projects without a video are not judged, so finish a short one first.

## What the judges score, and the shot that answers it

| Criterion | Shot |
|---|---|
| Privacy (Privacy-First) | Wifi off on camera. Local review still runs. Show what is sent out (search terms only). |
| Search done right (Surge) | Exa/Tavily finds the pages. Click a citation and the live page has the same text. |
| Real user, real problem | Say who uses it: security engineers at companies, with checks set by industry (financial services, healthcare, government, retail). |
| Execution and demo | Say what is real and what isn't built yet. |

## Rules for the edit

1. Say what you're doing as you do it. Plain sentences, no slogans.
2. Every voiceover line goes with the action on screen at that moment.
3. Cut every wait. Speed up the scan progress card and say "sped up".
4. Move the cursor slowly. Zoom 1.5–2× only on the thing you're describing.
5. Record the screen first with no audio, then record the voiceover while watching the playback.
6. Add captions. Some judges watch muted.

## Before you hit record (15 min)

- [ ] Engine, web app and Ollama running. `curl -s http://127.0.0.1:8787/v1/health` returns ok.
- [ ] Settings → company saved, industry chosen. Exa or Tavily key present.
- [ ] Delete old scans (Scan page → clear all).
- [ ] Dry run every scan you'll show. Page memory reuses recent results; if a recorded result came from memory, say so.
- [ ] Test the wifi-off step before recording it. If it errors instead of listing public search under "What didn't finish", skip it.
- [ ] Browser: one window, no other tabs, bookmarks bar hidden, zoom 110–125%, 1920×1080.
- [ ] Do Not Disturb on, Dock hidden, no notifications.
- [ ] Claude Code terminal: 18pt+ font, cleared.
- [ ] Recorder: Screen Studio or Cap (auto-zoom on clicks), or QuickTime (⌘⇧5) with zooms added in the editor.

## Shot list and voiceover

### 0:00–0:20 What Tracefold is

[SCREEN] Tracefold Scan page, "Drop files to check".

[VO] "This is Tracefold, a platform that catches, fixes and prevents security risks in a company's files, both in
documents you upload and in code as you write it, through an MCP server your coding assistant connects to. Scans can
run on a schedule, so it keeps checking. It finds data breaches of internal files, and sensitive data inside
them, like API keys, access tokens and Social Security numbers. It searches the web for pages that
have leaked text from your files, and drafts a takedown request to each site. It disables leaked AWS keys and
revokes leaked GitHub tokens. And through your coding assistant, it removes secrets from code and rechecks the fix.
Takedowns and key changes go out after one click of approval. Your files never leave your laptop."

### 0:20–0:35 Who it's for

[SCREEN] Settings → Company → Edit → open the Industry menu (Financial services, Healthcare, Government and public
sector, Retail and e-commerce, Technology). Hover Healthcare so the line under it reads "Also checks for: medical
record numbers, provider NPIs and dates of birth". Cancel.

[VO] "It's built for security engineers at companies: the people who have to find out when internal documents or code
end up public, and get them taken down. Each company picks its industry, like financial services or healthcare, and
Tracefold adds checks for the regulated data that industry handles, like card numbers or medical record numbers."

### 0:30–1:10 Uploading a file and finding public copies

[SCREEN] Sample files → Duolingo memo → progress card (sped up) → results: site count, timeline of sites, matches
grouped by page. Zoom on the "Searched for" line. Click a citation; the live page opens; zoom on the matching sentence.

[VO] "We're uploading a sample file: a Duolingo internal memo whose text was later quoted in the press. The scan is
sped up here. Tracefold sends search queries to Exa and Tavily. This line shows exactly what was searched: the
company name, not the file. It downloads the pages that come back and compares them with the file locally. Here are
the sites that contain text from the memo, and the matching passages. Clicking a result opens the live page, and you
can see the same sentence."

### 1:10–1:35 Risks in the files, and approving a takedown

[SCREEN] Potential risks section → Approvals page → takedown draft → Approve → "saved as a file, not sent".

[VO] "Below that are risks the local model found in the file itself. This runs in Ollama on this laptop. For each
public copy, Tracefold drafts a takedown request to the site. A person has to approve it. In this demo, approved
requests are saved to a local folder, not emailed."

### 1:35–1:45 Scheduled checks

[SCREEN] Finished scan → Schedule → "every day" → Schedule. Cut to Settings → Scheduled checks: the file, "Every day",
next run, Run now / Pause / Delete.

[VO] "Any scan can run on a schedule, every hour, day or week, like a scheduled task. Tracefold keeps a private copy
of the files on this machine so it can check them again, and new results show up like any other scan."

### 1:45–2:05 The same checks from Claude Code (MCP)

[SCREEN] Claude Code terminal. Paste the scan prompt. Tool calls: `scan_changes` → `get_findings` → edit → `recheck_fix`.
Cut to the web app showing the same finding marked fixed.

[VO] "Tracefold runs as an MCP server, so a coding assistant can call it. Here Claude Code scans the uncommitted
changes in a repo, gets a finding, fixes the code, and rechecks it. The web app shows the same finding, now fixed.
The assistant can scan and fix code. It can't approve takedowns; only a person can."

### 2:05–2:30 Wifi off

[SCREEN] Turn Wi-Fi off (zoom on the icon). Run a scan. Local review completes. "What didn't finish" lists public search.

[VO] "Now wifi is off. We scan another file. Parsing, matching and the model review still finish, because they all run
on this laptop. Public search needs the internet, so it's listed as not finished instead of being reported as clean.
One limitation: Claude Code is a cloud assistant, so the results it receives go to Anthropic. A fully private setup
would use a local-model assistant, which we haven't shown here."

### 2:30–2:45 What's real

[SCREEN] End card. **Working:** file scans, Exa/Tavily search, local matching, Ollama review, industry checks,
scheduled checks, MCP scan/fix/recheck, approvals saved to a local folder. **Not built yet:** GitHub and Docs
connectors, a local-model assistant. Sample files are public company documents saved as files.

[VO] "Everything shown ran live. The sample files are public company documents saved as files. Connectors for GitHub
and Docs are not built yet."

## Voiceover recording

- One narrator is easiest. If you split it, switch at a section boundary.
- Small quiet room. A phone voice memo held about 15 cm from your mouth beats a laptop mic.
- Normal speaking voice, slightly slower than usual.
- Record each section 2–3 times and keep the best take.
- No music.

## Time budget (3 hours left)

| By | Done |
|---|---|
| +0:20 | Checklist, dry run of every scan, wifi-off test |
| +1:00 | Screen recorded in 7 clips, one per section |
| +1:25 | Voiceover recorded while watching the clips |
| +2:05 | Edit: cut waits, zooms, captions, end card. Export 1080p MP4 |
| +2:20 | Upload to YouTube as Unlisted, paste link in Devpost |
| +2:30 | Devpost text follows the same order as the video |
