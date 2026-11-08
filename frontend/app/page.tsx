import { ArrowRight, ArrowUpRight, Bot } from "lucide-react";
import { siClaude, siGithubcopilot, siOpenai } from "simple-icons";
import { Carousel, CarouselItem, CloudTransition, Ticker } from "@/components/motion";
import { Mission, Reveal, SiteFooter, SiteHeader } from "@/components/site";
import { PlatformLogos } from "@/components/platforms";
import { AgentOnboard } from "@/components/agent-onboard";
import { ImageSlot, LinkButton, Wordmark, cx } from "@/components/ui";

const EDGE = "px-[max(32px,4vw)]";

// Temporary preview art from 0.security, kept in public/preview/ (git-ignored). Replace with our own before publishing.
const ART = (name: string) => `/preview/${name}.webp`;
const LOOP_ART = ["soft-hero", "cloud-field", "workflow-dusk-soft-halftone-v3", "dependency-security-20261020", "pointillist-hero"].map(ART);
const STEP_ART = ["cloud-dusk", "cloud-field", "workflow-verification-20261030", "workflow-memory-20261030"].map(ART);
const COMPARE_ART = ["comparison-impact-20261026", "comparison-discovery-20261026", "comparison-stack-20261026", "comparison-fixes-20261026"].map(ART);
const H2 = "text-[clamp(32px,3.4vw,46px)] leading-[1.14] tracking-[-0.035em]";

// What the engine's checks flag today (server/tracefold/checks/rules.py and the passage matcher).
const DETECTS = [
  "Passages copied from your documents", "Code copied onto public pages", "AWS access keys", "GitHub tokens", "Slack tokens",
  "Stripe live keys", "Private key blocks", "Hard-coded passwords", "Hard-coded API keys", "Secrets written to logs",
  "Card numbers written to logs", "\"Confidential\" markers", "Social Security numbers",
];

// Real limits and rules from the engine, not marketing numbers.
const STATS: [string, string][] = [
  ["20", "public pages compared per scan, each with its fetch time"],
  ["15 min", "before uploaded text expires from memory"],
  ["1", "local model reviews findings, with no cloud fallback"],
  ["0", "takedowns sent or keys disabled without a named approver"],
];

// Verbatim quotes, each checked against its primary source. Don't edit the wording.
const QUOTES = [
  {
    text: "The explosion of leaked secrets represents one of the most significant yet underestimated threats in cybersecurity.",
    who: "Eric Fourrier",
    org: "CEO, GitGuardian · 2025",
    href: "https://blog.gitguardian.com/the-state-of-secrets-sprawl-2025-pr",
  },
  {
    text: "Microsoft's AI research team, while publishing a bucket of open-source training data on GitHub, accidentally exposed 38 terabytes of additional private data.",
    who: "Hillai Ben-Sasson & Ronny Greenberg",
    org: "Wiz Research · 2023",
    href: "https://www.wiz.io/blog/38-terabytes-of-private-data-accidentally-exposed-by-microsoft-ai-researchers",
  },
  {
    text: "An intruder was able to access consumers' personal information … using an access key that one of Respondent's engineers had publicly posted to GitHub.",
    who: "U.S. Federal Trade Commission",
    org: "Complaint, In the Matter of Uber Technologies",
    href: "https://www.ftc.gov/system/files/documents/cases/1523054_uber_technologies_revised_complaint_0.pdf",
  },
];

const FACTS = [
  { n: "28.65M", text: "new hardcoded secrets were added to public GitHub commits in 2025 alone.", href: "https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026/" },
  { n: "64%", text: "of valid secrets from 2022 are still not revoked in 2026.", href: "https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026-pr/" },
  { n: "~28%", text: "of incidents originate from leaks in collaboration and productivity tools, not repositories.", href: "https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026-pr/" },
];

// Shaped like the engine's outbound ledger: every request, its purpose and what happened.
const EGRESS = [
  ["GET", "forum.example/t/123", "public page fetch", "200"],
  ["POST", "127.0.0.1:11434/api/chat", "local model review", "200"],
  ["GET", "tracker.example/r?u=…", "redirect off the approved list", "DENIED"],
  ["WRITE", "outbox/act_4c2e.eml", "takedown request (approved)", "SAVED"],
  ["POST", "iam.amazonaws.com", "disable key (approved)", "200"],
];

const LIMITS = [
  ["Your files don't go to the search providers", "Public pages are fetched by a separate worker that only receives approved URLs.", "The URLs you choose to check can hint at what you care about."],
  ["Uploads stay in memory", "Uploaded bytes aren't written to disk, and they expire 15 minutes after the scan.", "This doesn't cover OS swap or crash dumps."],
  ["Matches are exact passages", "Every public match shows the copied text, your file and lines, and the page it's on.", "Edited or paraphrased copies aren't detected yet."],
  ["Coding assistants see only what you allow", "Minimal disclosure withholds paths, explanations and evidence text.", "A cloud-hosted assistant still sees titles, rule IDs and coverage."],
];

// ---------- small product windows used as illustrations ----------
function Win({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cx("flex w-full flex-col overflow-hidden rounded-[10px] border border-[#323837] bg-[#131615] text-[12px] shadow-[0_12px_32px_rgb(0_0_0/0.25)]", className)}>
      <div className="flex items-center justify-between border-b border-[#262b2a] px-3.5 py-2.5 text-[11.5px]">
        <span className="font-medium text-ink">Tracefold</span>
        <span className="text-faint">{title}</span>
      </div>
      <div className="flex-1 p-3.5">{children}</div>
    </div>
  );
}

function SevRow({ sev, label, meta, tag }: { sev: "critical" | "medium"; label: string; meta: string; tag: string }) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-line bg-panel-2 px-3 py-2.5">
      <span className={cx("h-6 w-[3px] rounded-full", sev === "critical" ? "bg-crit" : "bg-med")} />
      <span className="min-w-0 flex-1">
        <span className="block font-medium text-ink">{label}</span>
        <span className="block truncate text-[11px] text-faint">{meta}</span>
      </span>
      <span className={cx("text-[11px]", sev === "critical" ? "text-crit" : "text-med")}>{tag}</span>
    </div>
  );
}

const LOOP = [
  {
    title: "Find the copy",
    body: "Each scan compares your documents and code with the public pages you approve. A copied passage becomes one finding, with the page it's on.",
    win: (
      <Win title="Findings">
        <div className="space-y-2">
          <SevRow sev="critical" label="Matching content found publicly" meta="roadmap.md · lines 5–7 · forum.example" tag="Public" />
          <SevRow sev="medium" label="Sensitive value written to logs" meta="billing.py · line 7" tag="Your files" />
        </div>
      </Win>
    ),
  },
  {
    title: "See the evidence",
    body: "Your passage and the public copy side by side, with the URL and the time the page was fetched.",
    win: (
      <Win title="Evidence">
        <div className="space-y-1.5 font-mono text-[11.5px] text-ink-2">
          <p className="text-faint">roadmap.md · lines 5–7</p>
          <p>
            …we will <span className="rounded border border-local-line bg-local-bg px-1 text-local">retire the Harbor ingestion cluster</span>…
          </p>
          <p className="text-faint">forum.example/t/123 · fetched 14:02 UTC</p>
        </div>
      </Win>
    ),
  },
  {
    title: "Catch risks before they ship",
    body: "Secrets in code, sensitive values in logs and confidential markers are flagged with a suggested fix, even when nothing is public yet.",
    win: (
      <Win title="Potential risks">
        <div className="space-y-1.5 font-mono text-[11.5px]">
          <p className="text-ink-2">billing.py:7</p>
          <p className="text-faint">logger.info(&quot;charging card %s&quot;, card_number)</p>
          <p className="text-med">py_sensitive_logging · medium</p>
          <p className="text-local">fix: log mask(card_number) instead</p>
        </div>
      </Win>
    ),
  },
  {
    title: "Approve the takedown",
    body: "Tracefold drafts the removal request for every public copy. One approval sends it to the host's abuse contact.",
    win: (
      <Win title="Approvals">
        <ol className="space-y-2">
          {["Removal request for forum.example", "Disable AWS key ****4K4Z", "Recheck after the fix"].map((t, i) => (
            <li key={t} className="flex items-center gap-2.5 text-ink-2">
              <span className="font-mono text-[11px] text-accent">{String(i + 1).padStart(2, "0")}</span>
              {t}
            </li>
          ))}
        </ol>
      </Win>
    ),
  },
  {
    title: "See what left",
    body: "Every outbound request is in the ledger with its purpose. Redirects to hosts you didn't approve are refused.",
    win: (
      <Win title="Ledger">
        <div className="space-y-1.5 font-mono text-[11.5px]">
          {[
            ["public page fetch", "200"],
            ["local model review", "200"],
            ["redirect off the list", "DENIED"],
          ].map(([p, d]) => (
            <div key={p + d} className="flex justify-between">
              <span className="text-ink-2">{p}</span>
              <span className={d === "DENIED" ? "text-crit" : "text-faint"}>{d}</span>
            </div>
          ))}
        </div>
      </Win>
    ),
  },
];

const STEPS = [
  {
    n: "01",
    title: "Upload files, or capture your changes",
    body: "Drop in documents and code, or let your coding assistant capture Git changes. Everything is read once and held in memory.",
    win: (
      <Win title="Upload">
        <div className="space-y-2">
          {[
            ["roadmap.md", "captured"],
            ["proposal-q4.docx", "captured"],
            ["billing.py", "captured"],
          ].map(([l, h]) => (
            <div key={l} className="flex items-center justify-between rounded-md border border-local-line bg-local-bg px-2.5 py-1.5">
              <span className="text-ink">{l}</span>
              <span className="font-mono text-local">{h}</span>
            </div>
          ))}
        </div>
      </Win>
    ),
  },
  {
    n: "02",
    title: "Compare with the public pages you approve",
    body: "A separate worker fetches only the URLs on your approved list. Your files never go with it.",
    win: (
      <Win title="Sources">
        <div className="space-y-1.5 font-mono text-[11.5px]">
          {[
            ["forum", "fresh · 200"],
            ["vendor_blog", "fresh · 200"],
            ["archive", "failed · timeout"],
          ].map(([id, st]) => (
            <div key={id} className="flex justify-between rounded border border-line px-2 py-1">
              <span className="text-ink">{id}</span>
              <span className={st.startsWith("failed") ? "text-med" : "text-faint"}>{st}</span>
            </div>
          ))}
        </div>
      </Win>
    ),
  },
  {
    n: "03",
    title: "Review on your machine",
    body: "Exact matching and risk rules run first. A local model then reviews each candidate and has to cite the evidence.",
    win: (
      <Win title="Review">
        <div className="space-y-1.5 font-mono text-[11.5px]">
          <p className="text-faint">exact match: 41 tokens, 92% of passage</p>
          <p className="text-local">✓ evidence cited · supported</p>
          <p className="truncate text-ink">model: qwen2.5:7b on 127.0.0.1</p>
        </div>
      </Win>
    ),
  },
  {
    n: "04",
    title: "Approve the fix and recheck",
    body: "Approve the drafted takedown or key disable. After you fix a file, the same check runs again on the new version.",
    win: (
      <Win title="Recheck">
        <div className="space-y-2">
          <SevRow sev="medium" label="billing.py" meta="Not detected in the checked version" tag="Recheck" />
          <SevRow sev="critical" label="forum.example" meta="Takedown submitted · awaiting removal" tag="Public" />
        </div>
      </Win>
    ),
  },
];

const AGENTS = [
  { icon: siClaude, name: "Claude Code" },
  { icon: siOpenai, name: "Codex" },
  { icon: siGithubcopilot, name: "GitHub Copilot" },
];

const COMPARE_SELF: [string, string][] = [
  ["You'd paste internal documents into a third-party model.", "Your files are read by an engine and a model running in your own environment."],
  ["It only sees what its search tool happens to surface.", "Your text is compared with the exact public pages you approve, each with its URL and fetch time."],
  ["It can't show you the copy.", "Every match shows the copied passage side by side with your file and lines."],
  ["It can't do anything about it.", "Tracefold drafts the takedown and can disable a leaked AWS key, each after one approval."],
  ["There's no record of what was sent.", "Every outbound request is in the ledger, with its purpose and result."],
];

const COMPARE = [
  ["Scan only your own repositories", "Check whether your documents and code already appear on public pages"],
  ["Alert on every pattern match", "Show the exact copied passage and where it lives"],
  ["Leave the cleanup to you", "Draft the takedown and disable the leaked key, one approval each"],
  ["Upload your files to a vendor's cloud", "Run the engine and the model in your own environment"],
];

export default function Landing() {
  return (
    <div className="bg-bg">
      <SiteHeader />

      {/* Hero */}
      <section className="relative isolate flex min-h-[100svh] flex-col">
        <ImageSlot label="Hero image" src={ART("soft-hero")} className="absolute inset-0 -z-20" />
        {/* the image dissolves toward the bottom: progressive blur + darkening into the page */}
        <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 backdrop-blur-xl [mask-image:linear-gradient(to_top,black_0%,transparent_45%)]" />
        <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 bg-[linear-gradient(to_bottom,transparent_22%,rgb(0_0_0/0.2)_42%,rgb(0_0_0/0.73)_68%,#0a0c0c_100%)]" />
        <div className={cx("flex flex-1 flex-col justify-end pb-[clamp(40px,8vh,96px)] pt-[104px]", EDGE)}>
          <div className="mx-auto w-full max-w-[1760px]">
            <h1 className="rise max-w-[15ch] text-[clamp(44px,5vw,72px)] font-semibold leading-none tracking-[-0.04em] text-white" style={{ animationDelay: "140ms" }}>
              Find your company&apos;s documents and code on the public web.
            </h1>
            <p className="rise mt-6 max-w-[34rem] text-[clamp(17px,1.4vw,20px)] leading-[1.5] text-[#c2c3c7]" style={{ animationDelay: "240ms" }}>
              Tracefold checks your files against the public pages you choose and shows exactly what was copied and where. It flags risky changes
              before they ship, and drafts the takedown for you to approve. The engine and the model run in your environment.
            </p>
            <div className="rise mt-8 flex flex-wrap items-center gap-3" style={{ animationDelay: "340ms" }}>
              <LinkButton href="/setup" size="lg">
                Get started <ArrowRight className="size-4" aria-hidden />
              </LinkButton>
              <LinkButton href="#how" variant="secondary" size="lg">
                How it works
              </LinkButton>
            </div>
            <div className="rise mt-[clamp(56px,10vh,120px)]" style={{ animationDelay: "480ms" }}>
              <p className="mb-6 text-center text-[13px] text-mute">Checks any public page you approve, including</p>
              <PlatformLogos />
            </div>
          </div>
        </div>
      </section>

      {/* The problem, in other people's words */}
      <section className={EDGE} aria-labelledby="problem">
        <div className="mx-auto max-w-[1760px]">
          <Reveal className="pt-[clamp(48px,6vw,88px)]">
            <h2 id="problem" className={cx(H2, "max-w-3xl text-ink")}>
              Internal material ends up in public every day. Most teams hear about it from someone else.
            </h2>
          </Reveal>
          <div className="mt-12 grid gap-4 lg:grid-cols-3">
            {QUOTES.map((q, i) => (
              <Reveal key={q.who} delay={i * 80} className="h-full">
                <figure className="flex h-full flex-col justify-between rounded-[24px] border border-line bg-[#090a0c] p-7">
                  <blockquote className="text-[clamp(18px,1.4vw,21px)] leading-[1.4] tracking-[-0.02em] text-ink">&ldquo;{q.text}&rdquo;</blockquote>
                  <figcaption className="mt-8 flex items-end justify-between gap-4 border-t border-line pt-5">
                    <span>
                      <span className="block text-sm font-medium text-ink">{q.who}</span>
                      <span className="mt-0.5 block text-[13px] text-faint">{q.org}</span>
                    </span>
                    <a href={q.href} target="_blank" rel="noreferrer" className="inline-flex shrink-0 items-center gap-1 text-[13px] text-mute transition-colors hover:text-ink">
                      Source <ArrowUpRight className="size-3.5" aria-hidden />
                    </a>
                  </figcaption>
                </figure>
              </Reveal>
            ))}
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            {FACTS.map((f, i) => (
              <Reveal key={f.n} delay={i * 80} className="h-full">
                <a href={f.href} target="_blank" rel="noreferrer" className="group flex h-full flex-col rounded-[24px] border border-line bg-[#090a0c] p-7 transition-colors duration-200 hover:border-line-strong">
                  <span className="text-[clamp(36px,3.2vw,48px)] font-medium leading-none tracking-[-0.045em] text-ink">{f.n}</span>
                  <span className="mt-4 text-[15px] leading-snug text-ink-2">{f.text}</span>
                  <span className="mt-6 inline-flex items-center gap-1 text-[13px] text-faint group-hover:text-mute">
                    GitGuardian, State of Secrets Sprawl 2026 <ArrowUpRight className="size-3.5" aria-hidden />
                  </span>
                </a>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Proof: numbers straight from the product + what it detects */}
      <section className={cx("pb-10 pt-[clamp(80px,9vw,128px)]", EDGE)}>
        <Reveal className="mx-auto max-w-[900px] text-center">
          <h2 className="text-[clamp(28px,3vw,40px)] leading-[1.15] tracking-[-0.035em] text-ink">What every scan is held to.</h2>
        </Reveal>
        <div className="mx-auto mt-14 grid max-w-[1200px] grid-cols-2 gap-y-10 lg:grid-cols-4">
          {STATS.map(([n, label], i) => (
            <Reveal key={label} delay={i * 70} className="border-l border-line px-6">
              <p className="text-[clamp(32px,3vw,44px)] font-medium leading-none tracking-[-0.04em] text-accent">{n}</p>
              <p className="mt-3 max-w-[18ch] text-[15px] leading-snug text-mute">{label}</p>
            </Reveal>
          ))}
        </div>
        <div className="mx-auto mt-16 max-w-[1760px]">
          <p className="mb-5 text-center text-[13px] text-faint">Flags, among others</p>
          <Ticker items={DETECTS} />
        </div>
      </section>

      {/* Premise */}
      <section className="mx-auto w-[calc(100%-2*max(32px,4vw))] max-w-[1400px] pb-[clamp(80px,9vw,120px)] pt-16">
        <Reveal>
          <ImageSlot label="Premise art" src={ART("cloud-field")} position="center 40%" className="rounded-[28px] px-[clamp(24px,6vw,96px)] py-[clamp(56px,8vw,112px)] text-center">
            <p className="mx-auto max-w-[44rem] text-[20px] leading-[1.5] tracking-[-0.02em] text-[#b9babf]">
              Roadmaps get pasted into forums. Keys end up in public code. Proposals turn up on a vendor&apos;s blog.
            </p>
            <p className="mx-auto mt-6 max-w-[1100px] text-[clamp(32px,3.6vw,54px)] font-medium leading-[1.13] tracking-[-0.04em] text-ink">
              Tracefold finds the copy, shows you the evidence, and drafts the fix for you to approve.
            </p>
          </ImageSlot>
        </Reveal>
      </section>

      {/* Closes the loop */}
      <section className="pb-[clamp(80px,9vw,130px)]">
        <Carousel
          heading={
            <h2 className={cx(H2, "text-ink")}>
              Tracefold closes the loop:
              <br />
              <span className="text-faint">find the copy, show the evidence, and act on it.</span>
            </h2>
          }
        >
          {LOOP.map((c, i) => (
            <CarouselItem key={c.title}>
              <article className="relative isolate flex h-full flex-col overflow-hidden rounded-[24px] border border-line bg-[#090a0c]">
                <ImageSlot label="Card art" src={LOOP_ART[i % LOOP_ART.length]} className="absolute inset-0 -z-20" />
                <div aria-hidden className="absolute inset-0 -z-10 bg-[linear-gradient(180deg,transparent_25%,rgb(9_10_12/0.19)_44%,rgb(9_10_12/0.91)_65%,#090a0c_79%)]" />
                <div className="flex h-[clamp(300px,24vw,350px)] items-center justify-center">
                  <div className="h-[80%] w-[86%] [&>*]:h-full">{c.win}</div>
                </div>
                <div className="flex flex-col gap-2.5 px-[26px] pb-[22px] pt-3.5">
                  <h3 className="text-[21px] font-[550] leading-[1.2] tracking-[-0.025em] text-ink">{c.title}</h3>
                  <p className="text-[17px] leading-[1.5] tracking-[-0.01em] text-[#c3c4c8]">{c.body}</p>
                </div>
              </article>
            </CarouselItem>
          ))}
        </Carousel>
      </section>

      {/* Onboarding band */}
      <section className="mx-auto w-[calc(100%-2*max(20px,3vw))] max-w-[1300px] pb-9 pt-3">
        <Reveal>
          <h2 className="mx-auto mb-10 max-w-[1050px] text-center text-[clamp(34px,4.6vw,64px)] font-medium leading-[1.1] tracking-[-0.045em] text-[#eef3f1]">
            Set up in minutes.
          </h2>
          <div className="overflow-hidden rounded-[28px] border border-line bg-[#141414]">
            <ImageSlot label="Band image" src={ART("onboarding-clouds")} className="flex min-h-[clamp(260px,26vw,340px)] items-center justify-center px-5 py-10">
              <AgentOnboard />
            </ImageSlot>
            <div className="grid items-center gap-6 px-[clamp(24px,5vw,72px)] py-8 lg:grid-cols-[1fr_auto_1fr]">
              <p className="inline-flex flex-wrap items-center gap-x-2.5 text-[clamp(17px,1.5vw,21px)] text-ink-2">
                Upload your files
                <ArrowRight className="size-[1.05em] text-mute" aria-hidden />
                First scan in minutes
              </p>
              <LinkButton href="/setup" className="justify-self-start lg:justify-self-center">
                Get started
              </LinkButton>
              <p className="text-[clamp(18px,1.6vw,24px)] font-medium leading-snug tracking-[-0.02em] text-ink lg:justify-self-end">
                Runs on your machine
                <br />
                or in your cloud.
              </p>
            </div>
          </div>
        </Reveal>
      </section>

      <CloudTransition height={420} />

      {/* How it works (paper) */}
      <div className="bg-paper text-paper-ink">
        <section id="how" className={cx("scroll-mt-28 pb-[clamp(80px,9vw,130px)] pt-2", EDGE)}>
          <div className="mx-auto max-w-[1760px]">
            <Reveal>
              <h2 className="mb-[clamp(30px,4vw,56px)] text-[clamp(40px,5vw,72px)] leading-[1.02] tracking-[-0.055em]">How it works</h2>
            </Reveal>
            <ol className="grid gap-x-6 gap-y-14 sm:grid-cols-2 xl:grid-cols-4">
              {STEPS.map((s, i) => (
                <li key={s.n} className="row-span-4 grid grid-rows-subgrid gap-y-4">
                  <Reveal delay={i * 80} className="row-span-4 grid grid-rows-subgrid gap-y-4">
                    <ImageSlot label="Step art" src={STEP_ART[i]} className="flex aspect-[1.2/1] items-center justify-center rounded-2xl p-[7%]">
                      <div className="h-full w-full [&>*]:h-full">{s.win}</div>
                    </ImageSlot>
                    <p className="font-mono text-xs tracking-[0.08em] text-rust">STEP {s.n}</p>
                    <h3 className="text-[clamp(21px,1.9vw,25px)] leading-[1.24] tracking-[-0.025em]">{s.title}</h3>
                    <p className="text-base leading-[1.6] text-paper-mute">{s.body}</p>
                  </Reveal>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Why not just ask an AI assistant? */}
        <section className={cx("pb-[clamp(80px,9vw,130px)]", EDGE)}>
          <div className="mx-auto max-w-[1400px]">
            <Reveal>
              <h2 className={cx(H2, "mx-auto max-w-[20ch] text-center")}>Why not just ask ChatGPT or Claude?</h2>
            </Reveal>
            <Reveal delay={80} className="mt-12">
              <div className="grid grid-cols-[minmax(0,0.65fr)_minmax(0,1fr)] items-end pb-4 text-sm">
                <p className="px-5 text-paper-mute sm:px-9">Your AI assistant</p>
                <div className="px-5 text-paper-ink sm:px-9">
                  <Wordmark className="text-[13px] !text-paper-ink" />
                </div>
              </div>
              <div className="overflow-hidden rounded-[24px] border border-paper-line">
                {COMPARE_SELF.map(([you, us], i) => (
                  <div key={you} className={cx("grid grid-cols-[minmax(0,0.65fr)_minmax(0,1fr)]", i > 0 && "border-t border-paper-line")}>
                    <p className="flex items-center bg-[#e9efed] px-5 py-6 text-[15px] leading-snug text-paper-mute sm:px-9 sm:py-7 sm:text-[17px]">{you}</p>
                    <p className="flex items-center bg-paper-card px-5 py-6 text-[15px] leading-[1.6] text-paper-ink sm:px-9 sm:py-7 sm:text-[17px]">{us}</p>
                  </div>
                ))}
              </div>
            </Reveal>
          </div>
        </section>

        {/* Fits where the team already works: coding assistant over MCP */}
        <section className={cx("pb-10", EDGE)}>
          <div className="mx-auto grid max-w-[1400px] grid-cols-1 items-center gap-12 lg:grid-cols-[0.85fr_1.15fr] [&>*]:min-w-0">
            <Reveal>
              <h2 className={H2}>
                Catch it while you code.
                <span className="block text-paper-mute">Tracefold works inside your coding assistant.</span>
              </h2>
              <p className="mt-5 max-w-md text-base leading-[1.6] text-paper-mute">
                Connect Tracefold over MCP. Your assistant scans your changes before it says it&apos;s done, explains what it found, and rechecks the fix.
                You see the same findings here.
              </p>
              <ul className="mt-8 flex flex-wrap gap-x-7 gap-y-3 text-[15px] font-medium">
                {AGENTS.map(({ icon, name }) => (
                  <li key={name} className="inline-flex items-center gap-2">
                    <svg viewBox="0 0 24 24" className="size-[18px]" fill="currentColor" aria-hidden>
                      <path d={icon.path} />
                    </svg>
                    {name}
                  </li>
                ))}
              </ul>
            </Reveal>
            <Reveal delay={100}>
              <ImageSlot label="Integration art" src={ART("workflow-dusk-soft-halftone-v3")} position="30% 20%" className="rounded-[24px] p-[clamp(20px,5%,48px)]">
                <div className="space-y-3">
                  <Win title="Assistant">
                    <div className="flex items-center justify-between gap-3">
                      <span className="flex items-center gap-2.5">
                        <span className="h-6 w-[3px] rounded-full bg-med" />
                        <span>
                          <span className="block text-[13px] font-medium text-ink">Sensitive value written to logs</span>
                          <span className="block text-[11px] text-faint">billing.py · line 7 · from scan_changes</span>
                        </span>
                      </span>
                      <span className="inline-flex h-7 items-center gap-1.5 rounded-md bg-[#fafafa] px-2.5 text-[11.5px] font-medium text-[#0a0c0c]">
                        <Bot className="size-3.5" aria-hidden /> recheck_fix
                      </span>
                    </div>
                  </Win>
                  <Win title="Tool calls">
                    <p className="font-mono text-[11.5px] leading-[1.65] text-ink-2">
                      scan_changes(baseline=&quot;HEAD&quot;)
                      <br />
                      <span className="text-med">local_risk</span> billing.py:7 py_sensitive_logging
                      <br />
                      <span className="text-faint"># after the fix</span>
                      <br />
                      recheck_fix(fnd_91ab) →{" "}
                      <span className="rounded border border-local-line bg-local-bg px-1 text-local">not_detected_in_checked_version</span>
                    </p>
                  </Win>
                </div>
              </ImageSlot>
            </Reveal>
          </div>
        </section>
      </div>

      <CloudTransition reverse height={360} />

      {/* How files stay private */}
      <section className={cx("pb-[clamp(80px,9vw,130px)] pt-6", EDGE)}>
        <div className="mx-auto max-w-[1400px]">
          <Reveal>
            <h2 className={cx(H2, "max-w-3xl text-ink")}>How your files stay private.</h2>
            <p className="mt-5 max-w-xl text-base leading-[1.6] text-mute">Three mechanisms, each one visible in the product.</p>
          </Reveal>
          <div className="mt-12 grid gap-4 md:grid-cols-3">
            {[
              ["A local engine and model", "Parsing, matching and model review run in your environment. The model endpoint has to be on the same machine."],
              ["A separate public worker", "Public pages are fetched by their own process, which only receives approved URLs and never your files."],
              ["A ledger you can read", "Every outbound request is recorded with its purpose and result, including approved takedowns and key changes."],
            ].map(([t, d], i) => (
              <Reveal key={t} delay={i * 80} className="h-full">
                <article className="flex h-full flex-col rounded-[24px] border border-line bg-[#090a0c] p-7">
                  <h3 className="text-[21px] leading-tight tracking-[-0.025em] text-ink">{t}</h3>
                  <p className="mt-3 flex-1 text-[15px] leading-[1.6] text-mute">{d}</p>
                </article>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Traditional vs Tracefold */}
      <section className="pb-[clamp(80px,9vw,130px)]">
        <Carousel heading={<h2 className={cx(H2, "text-ink")}>How Tracefold differs from a typical secret scanner.</h2>}>
          {COMPARE.map(([trad, ours], i) => (
            <CarouselItem key={trad}>
              <article className="relative isolate flex min-h-[440px] flex-col justify-between overflow-hidden rounded-[24px] border border-line bg-[#0c0d10] p-8">
                <ImageSlot label="Card art" src={COMPARE_ART[i]} className="absolute inset-0 -z-20 opacity-70" />
                <div aria-hidden className="absolute inset-0 -z-10 bg-[linear-gradient(180deg,rgb(12_13_16/0.92)_0%,rgb(12_13_16/0.55)_45%,rgb(12_13_16/0.92)_100%)]" />
                <div>
                  <p className="text-sm text-faint">Traditional</p>
                  <p className="mt-3 text-[clamp(19px,1.6vw,23px)] leading-snug tracking-[-0.02em] text-mute">{trad}</p>
                </div>
                <div className="border-t border-line pt-6">
                  <p className="text-sm text-accent">With Tracefold</p>
                  <p className="mt-3 text-[clamp(19px,1.6vw,23px)] font-medium leading-snug tracking-[-0.02em] text-accent">{ours}</p>
                </div>
              </article>
            </CarouselItem>
          ))}
        </Carousel>
      </section>

      {/* What leaves your environment */}
      <section id="egress" className={cx("scroll-mt-28 pb-[clamp(80px,9vw,130px)]", EDGE)}>
        <div className="mx-auto grid max-w-[1760px] grid-cols-1 items-center gap-12 lg:grid-cols-[0.8fr_1.2fr] [&>*]:min-w-0">
          <Reveal>
            <h2 className={cx(H2, "text-ink")}>Every request that leaves is logged. Nothing goes anywhere you didn&apos;t approve.</h2>
            <p className="mt-5 max-w-md text-base leading-[1.6] text-mute">
              All outbound traffic goes through one gateway. It checks each destination against the approved list, refuses private addresses and
              unapproved redirects, and records the purpose of every request.
            </p>
          </Reveal>
          <Reveal delay={120}>
            <ImageSlot label="Panel art" src={ART("comparison-open-20261026")} className="rounded-[24px] border border-line p-[clamp(16px,4%,40px)]">
              <div className="overflow-hidden rounded-[10px] border border-[#323837] bg-[#131615] shadow-[0_12px_32px_rgb(0_0_0/0.25)]">
                <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-[#262b2a] px-4 py-3 font-mono text-xs">
                  <span className="text-ink">5 events</span>
                  <span className="text-local">0 private files sent</span>
                  <span className="text-crit">1 denied</span>
                </div>
                <table className="w-full text-left text-xs">
                  <tbody className="font-mono">
                    {EGRESS.map(([m, d, p, dec], i) => (
                      <tr key={i} className={cx("border-b border-[#1f2423] last:border-0", dec === "DENIED" && "bg-crit/[0.06]")}>
                        <td className="px-4 py-2.5 text-faint">{m}</td>
                        <td className="max-w-[220px] truncate py-2.5 pr-3 text-ink">{d}</td>
                        <td className="hidden py-2.5 pr-3 font-sans text-mute sm:table-cell">{p}</td>
                        <td className="px-4 py-2.5 text-right">
                          <span className={cx("rounded px-1.5 py-0.5 text-[10.5px] font-semibold tracking-wide", dec === "DENIED" ? "bg-crit/15 text-crit" : "text-faint ring-1 ring-line")}>{dec}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="border-t border-[#262b2a] px-4 py-3 text-xs text-mute">
                  Denied: the page redirected to <span className="text-ink">tracker.example</span>, which isn&apos;t on the approved list. Nothing was fetched from it.
                </p>
              </div>
            </ImageSlot>
          </Reveal>
        </div>
      </section>

      {/* Security model */}
      <section id="limits" className={cx("scroll-mt-28 border-t border-line py-[clamp(80px,9vw,130px)]", EDGE)}>
        <div className="mx-auto max-w-[1760px]">
          <Reveal>
            <h2 className={cx(H2, "max-w-3xl text-ink")}>What we claim, and where it stops.</h2>
            <p className="mt-4 max-w-xl text-base leading-[1.6] text-mute">
              A match shows that text appears on a page, not who put it there. No match means none in the sources checked.
            </p>
          </Reveal>
          <div className="mt-12 grid gap-4 md:grid-cols-2">
            {LIMITS.map(([claim, backs, limit], i) => (
              <Reveal key={claim} delay={(i % 2) * 80}>
                <article className="h-full rounded-[24px] border border-line bg-[#090a0c] p-7">
                  <h3 className="text-[21px] leading-[1.25] tracking-[-0.025em] text-ink">{claim}</h3>
                  <p className="mt-3 text-[15px] leading-[1.6] text-ink-2">{backs}</p>
                  <p className="mt-4 border-t border-line pt-4 text-sm leading-[1.6] text-mute">
                    <span className="text-faint">Limit: </span>
                    {limit}
                  </p>
                </article>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Built for security teams */}
      <section className={cx("pb-10", EDGE)}>
        <Reveal className="mx-auto max-w-[1760px]">
          <ImageSlot label="Team art" src={ART("cloud-dusk")} position="center 70%" className="rounded-[24px]">
            <div className="flex flex-wrap items-start justify-between gap-6 px-[clamp(24px,4vw,56px)] pt-[clamp(40px,6vw,96px)]">
              <div className="max-w-3xl">
                <h2 className="text-[clamp(34px,4vw,60px)] font-medium leading-[1.05] tracking-[-0.045em] text-white">Built for security teams</h2>
                <p className="mt-5 text-[clamp(16px,1.3vw,19px)] leading-[1.6] text-[#c2c3c7]">
                  Run it in your own environment, review every finding with its evidence, and approve each takedown or key change yourself.
                </p>
              </div>
              <LinkButton href="/scan" variant="secondary" className="border-white/20 bg-black/30 backdrop-blur">
                Open the app <ArrowRight className="size-4" aria-hidden />
              </LinkButton>
            </div>
            <div className="mt-[clamp(40px,6vw,96px)] grid gap-4 px-4 md:grid-cols-3">
              {[
                ["Runs in your environment", "The engine, the model and your files stay on your machine or in your cloud. Only approved public pages are fetched."],
                ["Approval before any action", "Takedown requests and key changes are drafted for you. Nothing is sent or changed until a named person approves."],
                ["Honest results", "Every scan lists what it checked and what it couldn't. It never calls a file safe or a problem fixed."],
              ].map(([t, d]) => (
                <div key={t} className="rounded-t-[18px] border border-b-0 border-line bg-[#111216] p-8 pb-12">
                  <h3 className="text-[clamp(21px,1.8vw,26px)] leading-tight tracking-[-0.025em] text-ink">{t}</h3>
                  <p className="mt-4 text-[16px] leading-[1.6] text-mute">{d}</p>
                </div>
              ))}
            </div>
          </ImageSlot>
        </Reveal>
      </section>

      <Mission />
      <SiteFooter />
    </div>
  );
}
