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

## Recording the web clips automatically

`demo/record.mjs` drives the real app and saves the web shots as 1080p clips in `demo/out/` (01 intro, 02 industry,
03 public copies, 04 risks and takedown, 05 schedule, 06 end card). Record the Claude Code and Wi-Fi-off shots by hand.

```bash
cd demo && npm install && npx playwright install chromium
```

```bash
node record.mjs --fresh
```

`--fresh` deletes finished scans first so clip 03 runs a real search. Re-record one clip with `node record.mjs 03`.

## Shot list and voiceover

Timed to the recorded clips in `demo/out/`. Times in brackets are seconds into each clip, so you can line the voice up
in the editor. About 2.5 words per second, plain spoken English.

### 0:00–0:22 · Clip 01 · Title card

[VO] "This is Tracefold. It helps you catch, fix and prevent security leaks. It checks if your company's documents or
code have ended up on public websites, finds secrets like API keys, and drafts takedowns and turns off leaked keys once
approved. Enterprises can run it in their own VPC or on their own machines, to keep their proprietary data private."

### 0:22–0:39 · Clip 02 · Choosing an industry

- [0s] "It's meant for a company's security team. Senior leads approve takedowns, and engineers can run scans."
- [4s, menu opens] "You pick your industry, and Tracefold adds checks for it."
- [8s, Healthcare chosen] "For healthcare, that's medical record numbers, provider IDs and dates of birth."

### 0:39–1:11 · Clip 03 · Finding public copies

Speed up 6s–19s (the scan running) to about 4 seconds and put "sped up" on screen.

- [0s] "Here's a sample memo from Duolingo. Parts of it were quoted in news articles."
- [3s, scan starts] "Tracefold searches the web for the company name using Exa or Tavily, then downloads the pages it finds and
  compares them locally with your documents and code."
- [21s, results] "It found the memo's text on four sites."
- [27s, timeline] "Each site shows which passages match."
- [33s, comparison] "Here's one: the same sentence, highlighted in the memo and on The Verge."

### 1:11–1:37 · Clip 04 · Risks in a file, and a takedown

- [0s] "It also flags risky content inside your files. This one is marked confidential."
- [6s, Approvals] "When a public page copies your file, Tracefold drafts a takedown request to that site."
- [11s, letter opens] "You can read the letter before it goes out."
- [16s, Save email] "One click approves it. In this demo, email sending is off, so it's saved as a file instead of sent."

### 1:37–1:48 · Clip 05 · Scheduled checks

[VO] "You can also set any scan to run again on a schedule, starting whenever you want."

### 1:48–2:08 · Claude Code over MCP (to record)

[SCREEN] Claude Code in a terminal, running the app's scan prompt: `scan_changes` → `get_findings` → edits the file →
`recheck_fix`. Cut to Findings showing "Not detected in checked version".

[VO] "Tracefold also works inside coding tools through MCP. Here, Claude Code checks my code changes, finds an AWS key,
moves it out of the code, and checks again. Claude Code can fix code, but it can't approve takedowns."

### 2:08–2:33 · Wi-Fi off (to record)

[SCREEN] Turn Wi-Fi off (zoom on the icon). Scan a sample file with "Also check public pages" ticked. Local checks
finish; "What didn't finish" lists the public check.

[VO] "Now Wi-Fi is off. The scan still finishes, because the matching and the AI model run on this computer. The web
search needs internet, so Tracefold says that part didn't finish. It doesn't call the file clean."

### 2:33–2:48 · Clip 06 · Title card

[VO] "Everything in this video ran live. The sample files are public company documents."

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
