import Link from "next/link";
import { ArrowRight, ArrowUpRight, Check } from "lucide-react";
import { EDGE, H2 } from "@/components/marketing";
import { PlatformLogos } from "@/components/platforms";
import { Reveal, SiteFooter, SiteHeader } from "@/components/site";
import { ImageSlot, LinkButton, cx } from "@/components/ui";

export const metadata = { title: "Enterprise · Tracefold" };

const REASONS = [
  ["Leaks are rising.", "28.65M", "new hardcoded secrets were added to public GitHub commits in 2025, a 34% increase on the year before.", "https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026/"],
  ["They stay valid.", "64%", "of valid secrets leaked in 2022 were still not revoked in 2026.", "https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026-pr/"],
  ["They're not only in code.", "~28%", "of incidents start in collaboration and productivity tools rather than repositories.", "https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026-pr/"],
];

const COVERAGE = [
  ["What you check", "Documents and code you upload in the web app, or the changes in a workspace, sent by your coding assistant."],
  ["Public sources", "Pages you approve, fetched through Exa, Tavily or directly. Every source is listed, and a failed fetch is shown as failed, never counted as clean."],
  ["Public matches", "Exact passages from your files found on a checked page, with your file and lines, the public URL, the matching text and when it was retrieved."],
  ["Risks in your files", "Secrets written into code, sensitive values sent to logs, confidential markers and personal data, each with a suggested change. Shown even when nothing matched publicly."],
  ["Local model review", "An Ollama model on your machine reviews each candidate and has to cite the evidence. Concerns raised only by the model are labelled for review."],
  ["Rechecks", "After you edit a file, Tracefold checks it again and reports still detected, not detected in the checked version, or inconclusive."],
  ["Not built yet", "Edited or paraphrased copies, scheduled monitoring, and connectors for GitHub and Docs."],
];

const STEPS = [
  ["Capture", "Upload files in the web app, or let your coding assistant send its changes. Private files stay in memory and expire after 15 minutes."],
  ["Fetch", "A separate worker fetches the public pages you approved. It never sees your files."],
  ["Match", "Passages are compared on your side, and every match keeps its evidence."],
  ["Review", "A local model reviews the candidates and flags risks in your files, citing the evidence."],
  ["Approve", "Takedown requests and key-disable actions are drafted. Nothing is sent or changed until a named person approves."],
];

const DEPLOY = [
  ["Your machine", "Run the scan engine, the local model and the app on one machine to try it on your own files."],
  ["Your trusted environment", "Run it inside your own network or private cloud, next to your other internal tools."],
  ["Managed setup", "We set it up with you, add your public sources and takedown contacts, and connect your coding assistant."],
];

const DEPLOY_FEATURES = [
  ["Data protection.", "Private uploads stay in memory and expire. Secret values are masked in evidence and never stored."],
  ["Egress control.", "Public pages are fetched by a separate worker with no access to your files, and the model runs on the same machine as the engine."],
  ["Access & audit.", "Token access with per-client permissions, and a ledger of every outbound request with its purpose."],
];

const DELIVERY = [
  ["Upload platform", "Every public match and potential risk, with its evidence, what was checked, and the actions waiting for approval."],
  ["MCP integration", "scan_changes, get_findings, explain_finding and recheck_fix inside coding assistants that support MCP, such as Claude Code."],
  ["Outbound ledger", "A record of every request Tracefold made, ready for your security review."],
];

export default function Enterprise() {
  return (
    <div className="bg-bg">
      <SiteHeader />

      {/* Opening */}
      <section className="relative isolate flex min-h-[86svh] flex-col">
        <ImageSlot label="Enterprise hero: tracing paper over documents on a light table, full bleed" className="absolute inset-0 -z-20" />
        <div aria-hidden className="absolute inset-0 -z-10 bg-[linear-gradient(to_bottom,transparent_25%,rgb(0_0_0/0.35)_50%,#0a0a0a_100%)]" />
        <div className={cx("flex flex-1 flex-col justify-end pb-14 pt-[120px]", EDGE)}>
          <div className="mx-auto w-full max-w-[1760px]">
            <h1 className="rise max-w-[16ch] text-[clamp(42px,5vw,72px)] font-semibold leading-[1.02] tracking-[-0.045em] text-white">
              Public-exposure checks for the whole company.
            </h1>
            <p className="rise mt-6 max-w-[40rem] text-[clamp(17px,1.4vw,20px)] leading-[1.55] text-[#c2c3c7]" style={{ animationDelay: "100ms" }}>
              Tracefold checks your documents and code against the public pages you approve, flags risks in your own files, and drafts the next step for a
              named person to approve. It runs in your environment and records every request it makes.
            </p>
            <div className="rise mt-8" style={{ animationDelay: "200ms" }}>
              <LinkButton href="/contact?topic=enterprise" size="lg">
                Talk to us <ArrowRight className="size-4" aria-hidden />
              </LinkButton>
            </div>
            <div className="rise mt-16" style={{ animationDelay: "300ms" }}>
              <p className="mb-5 text-[13px] text-mute">Checks the public pages you approve, on sites like these</p>
              <PlatformLogos className="lg:justify-start lg:gap-x-12" />
            </div>
          </div>
        </div>
      </section>

      {/* Why now */}
      <section className={cx("py-[clamp(80px,9vw,128px)]", EDGE)}>
        <div className="mx-auto max-w-[1760px]">
          <Reveal>
            <h2 className={cx(H2, "text-ink")}>3 reasons to check what&apos;s already public.</h2>
          </Reveal>
          <div className="mt-12 grid gap-4 md:grid-cols-3">
            {REASONS.map(([t, n, d, href], i) => (
              <Reveal key={t} delay={i * 80} className="h-full">
                <article className="flex h-full flex-col rounded-[24px] border border-line bg-[#090a0c] p-7">
                  <h3 className="text-[20px] font-medium tracking-[-0.025em] text-ink">{t}</h3>
                  <p className="mt-10 text-[clamp(44px,4vw,60px)] font-medium leading-none tracking-[-0.05em] text-accent">{n}</p>
                  <p className="mt-4 flex-1 text-[15px] leading-[1.6] text-mute">{d}</p>
                  <a href={href} target="_blank" rel="noreferrer" className="mt-6 inline-flex items-center gap-1 text-[13px] text-faint hover:text-ink">
                    GitGuardian, State of Secrets Sprawl 2026 <ArrowUpRight className="size-3.5" aria-hidden />
                  </a>
                </article>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Coverage */}
      <section className={cx("pb-[clamp(80px,9vw,128px)]", EDGE)}>
        <div className="mx-auto grid max-w-[1760px] gap-12 lg:grid-cols-[0.9fr_1.1fr]">
          <Reveal>
            <h2 className={cx(H2, "text-ink")}>From commits to the docs your team shares.</h2>
            <p className="mt-5 max-w-md text-base leading-[1.6] text-mute">
              Tracefold looks for two things: passages from your files that appear on public pages, and potential risks in the files themselves.
            </p>
          </Reveal>
          <dl className="divide-y divide-line border-y border-line">
            {COVERAGE.map(([t, d]) => (
              <Reveal key={t}>
                <div className="grid gap-2 py-6 sm:grid-cols-[180px_1fr] sm:gap-8">
                  <dt className="text-[17px] font-medium tracking-[-0.02em] text-ink">{t}</dt>
                  <dd className="text-[15px] leading-[1.6] text-mute">{d}</dd>
                </div>
              </Reveal>
            ))}
          </dl>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className={cx("pb-[clamp(80px,9vw,128px)]", EDGE)}>
        <div className="mx-auto max-w-[1760px]">
          <Reveal>
            <h2 className={cx(H2, "text-ink")}>How Tracefold works.</h2>
          </Reveal>
          <ol className="mt-12 grid gap-px overflow-hidden rounded-[24px] border border-line bg-line sm:grid-cols-2 lg:grid-cols-5">
            {STEPS.map(([t, d], i) => (
              <li key={t} className="bg-[#090a0c] p-7">
                <p className="font-mono text-xs tracking-[0.08em] text-accent">{String(i + 1).padStart(2, "0")}</p>
                <p className="mt-4 text-[19px] font-medium tracking-[-0.02em] text-ink">{t}</p>
                <p className="mt-2 text-[14.5px] leading-[1.6] text-mute">{d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Deployment */}
      <section className={cx("pb-[clamp(80px,9vw,128px)]", EDGE)}>
        <div className="mx-auto max-w-[1760px]">
          <Reveal>
            <h2 className={cx(H2, "text-ink")}>Deploy on your terms.</h2>
          </Reveal>
          <div className="mt-12 grid gap-4 md:grid-cols-3">
            {DEPLOY.map(([t, d], i) => (
              <Reveal key={t} delay={i * 80} className="h-full">
                <article className="relative isolate flex h-full min-h-[260px] flex-col justify-end overflow-hidden rounded-[24px] border border-line p-7">
                  <ImageSlot label="Deployment art: tracing paper over a building plan" className="absolute inset-0 -z-20" />
                  <div aria-hidden className="absolute inset-0 -z-10 bg-[linear-gradient(180deg,transparent_20%,#090a0c_85%)]" />
                  <h3 className="text-[22px] font-medium tracking-[-0.025em] text-white">{t}</h3>
                  <p className="mt-2 text-[15px] leading-[1.6] text-ink-2">{d}</p>
                </article>
              </Reveal>
            ))}
          </div>
          <div className="mt-10 grid gap-8 md:grid-cols-3">
            {DEPLOY_FEATURES.map(([t, d]) => (
              <Reveal key={t}>
                <p className="text-[15px] leading-[1.6] text-mute">
                  <span className="font-medium text-ink">{t}</span> {d}
                </p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Delivery */}
      <section className={cx("pb-[clamp(80px,9vw,128px)]", EDGE)}>
        <div className="mx-auto max-w-[1760px]">
          <Reveal>
            <h2 className={cx(H2, "text-ink")}>Delivered where your team works.</h2>
          </Reveal>
          <div className="mt-12 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <ul className="divide-y divide-line rounded-[24px] border border-line bg-[#090a0c]">
              {DELIVERY.map(([t, d]) => (
                <li key={t} className="flex gap-4 p-7">
                  <Check className="mt-1 size-5 shrink-0 text-accent" aria-hidden />
                  <div>
                    <p className="text-[18px] font-medium tracking-[-0.02em] text-ink">{t}</p>
                    <p className="mt-1 text-[15px] leading-[1.6] text-mute">{d}</p>
                  </div>
                </li>
              ))}
            </ul>
            <div className="grid gap-4">
              {[
                ["Dedicated support", "Work directly with the team that builds Tracefold, under an agreed SLA."],
                ["Takedown contacts", "Tell us which hosts matter to you, and we'll help you set up their abuse or legal contacts."],
              ].map(([t, d]) => (
                <article key={t} className="rounded-[24px] border border-line bg-[#111216] p-7">
                  <p className="text-[18px] font-medium tracking-[-0.02em] text-ink">{t}</p>
                  <p className="mt-1 text-[15px] leading-[1.6] text-mute">{d}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Closing */}
      <section className={cx("pb-[clamp(80px,9vw,128px)]", EDGE)}>
        <div className="mx-auto grid max-w-[1760px] gap-4 lg:grid-cols-[1.3fr_1fr]">
          <Reveal className="h-full">
            <ImageSlot label="Closing art: a single folded sheet of tracing paper on a dark desk" className="flex h-full min-h-[320px] flex-col justify-end rounded-[24px] border border-line p-[clamp(28px,4vw,48px)]">
              <h2 className="max-w-[20ch] text-[clamp(30px,3.2vw,46px)] font-medium leading-[1.1] tracking-[-0.04em] text-white">
                Public-exposure checks, run in your environment.
              </h2>
              <div className="mt-6">
                <LinkButton href="/contact?topic=enterprise">
                  Talk to us <ArrowRight className="size-4" aria-hidden />
                </LinkButton>
              </div>
            </ImageSlot>
          </Reveal>
          <Reveal delay={100} className="h-full">
            <article className="flex h-full flex-col rounded-[24px] border border-line bg-[#090a0c] p-[clamp(28px,4vw,40px)]">
              <h2 className="text-[24px] font-medium tracking-[-0.03em] text-ink">Start directly, or evaluate first.</h2>
              <ul className="mt-6 flex-1 space-y-5 text-[15px] leading-[1.6] text-mute">
                <li>
                  <span className="font-medium text-ink">Book a walkthrough.</span> We run a scan with you on sample documents and review the findings together.
                </li>
                <li>
                  <span className="font-medium text-ink">Start on Starter.</span> Run it yourself on your own files and see what it finds.
                </li>
              </ul>
              <div className="mt-8 flex flex-wrap gap-3">
                <LinkButton href="/contact?topic=enterprise" variant="secondary">
                  Book a walkthrough
                </LinkButton>
                <Link href="/onboarding" className="inline-flex h-10 items-center gap-1.5 px-2 text-sm text-ink hover:underline hover:underline-offset-4">
                  Start free <ArrowRight className="size-4" aria-hidden />
                </Link>
              </div>
            </article>
          </Reveal>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
