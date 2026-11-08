# Tracefold demo video: plan, shot list and voiceover

Target length **about 2:45**. The rules say projects without a video are not judged, so finish a short one first.

## What the judges score, and the shot that answers it

| Criterion | Shot |
|---|---|
| Privacy (Privacy-First) | Wifi off on camera. Local review still runs. Show what is sent out (search terms only). |
| Search done right (Surge) | Exa/Tavily finds the pages. Click a citation and the live page has the same text. |
| Real user, real problem | Say who buys and uses it: bought by the head of security (CISO); used by senior security leaders who can approve takedowns; engineers and coding assistants scan but can't approve. Checks set by industry. |
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

About 2.5 words per second, in plain spoken English. Word counts are in brackets.

### 0:00–0:22 What Tracefold is

[SCREEN] Tracefold Scan page.

[VO] "This is Tracefold. It checks if your company's documents or code have ended up on public websites. It also finds secrets, like API keys, inside your files. It can draft takedowns and turn off leaked keys, once someone approves. You can run it on your own computer or on your company's servers, so your private files and data stay with you." [61]

### 0:22–0:35 Who it's for

[SCREEN] Settings → Company → Edit → open the Industry menu. Hover Healthcare so the line under it reads "Also checks
for: medical record numbers, provider NPIs and dates of birth". Cancel.

[VO] "It's meant for a company's security team. Senior leads approve takedowns. Engineers can run scans, but they can't approve them. You pick your industry, and Tracefold adds checks for it, like medical record numbers for healthcare." [36]

### 0:35–1:10 Finding public copies

[SCREEN] Sample files → Duolingo memo → progress card (sped up) → "3 public sites show text from your documents" →
timeline. Zoom on "Searched for Duolingo". Open a site's passages, then Open page; zoom on the highlighted sentence.

[VO] "This is a sample memo from Duolingo. Parts of it were quoted in news articles. Tracefold searches the web for the company name, using Exa or Tavily. Your files are never sent anywhere. It downloads the pages it finds and compares them with the file on this computer. It found the memo's text on three sites. If I open one, you can see the same sentence highlighted." [67]

### 1:10–1:35 Risks in the file, and approving a takedown

[SCREEN] "In your files" section. Then Approvals → the pastebin.com takedown (from the sample page list; search-found
pages don't get takedown drafts yet) → See the letter → the approve button reads "Save email" because sending is off.

[VO] "It also checks the file for risky content, using an AI model that runs on this computer. When a page copies your file, Tracefold writes a takedown request. Someone on the security team approves it with one click. In this demo, the request is saved as a file instead of being emailed." [52]

### 1:35–1:45 Scheduled checks

[SCREEN] Finished scan → Schedule → "every 1 days", start time → Schedule. Cut to Settings → Scheduled checks.

[VO] "You can also set any scan to run again on a schedule, as often as you need." [17]

### 1:45–2:05 Claude Code over MCP

[SCREEN] Claude Code terminal. Paste the scan prompt. Tool calls: `scan_changes` → `get_findings` → edit →
`recheck_fix`. Cut to the web app showing the finding fixed.

[VO] "Tracefold also works inside coding tools, through MCP. Here, Claude Code checks my code changes, finds a secret, removes it, and checks again. The app shows it as fixed. Claude Code can fix code, but it can't approve takedowns." [39]

### 2:05–2:30 Wi-Fi off

[SCREEN] Turn Wi-Fi off (zoom on the icon). Run a scan. Local checks finish; "What didn't finish" lists the public
check.

[VO] "Now I'll turn Wi-Fi off and scan another file. The scan still finishes, because the matching and the AI model run on this computer. The web search needs internet, so Tracefold says that part didn't finish. It doesn't call the file clean." [42]

### 2:30–2:45 What's real

[SCREEN] End card. **Working:** file scans, Exa or Tavily search, local matching, Ollama review, industry checks, scheduled
checks, MCP scan/fix/recheck, takedowns saved to a local folder. **Not built yet:** takedown drafts for
search-found pages, a local-model coding assistant. **Note:** Claude Code is a cloud assistant,
so results it reads go to Anthropic. Sample files are public company documents saved as files.

[VO] "Everything in this video ran live. The sample files are public company documents." [13]

## Voiceover recording

- One narrator is easiest. If you split it, switch at a section boundary.
- Small quiet room. A phone voice memo held about 15 cm from your mouth beats a laptop mic.
- Normal speaking voice, slightly slower than usual.
- Record each section 2–3 times and keep the best take.
- No music.

## Time budget

| By | Done |
|---|---|
| +0:20 | Checklist, dry run of every scan, wifi-off test |
| +1:00 | Screen recorded in 7 clips, one per section |
| +1:25 | Voiceover recorded while watching the clips |
| +2:05 | Edit: cut waits, zooms, captions, end card. Export 1080p MP4 |
| +2:20 | Upload to YouTube as Unlisted, paste link in Devpost |
| +2:30 | Devpost text follows the same order as the video |
