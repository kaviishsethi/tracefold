import { ArrowRight, ArrowUpRight } from "lucide-react";
import { EDGE, H2 } from "@/components/marketing";
import { Carousel, CarouselItem } from "@/components/motion";
import { Reveal, SiteFooter, SiteHeader } from "@/components/site";
import { ImageSlot, LinkButton, cx } from "@/components/ui";

export const metadata = { title: "Security · Tracefold" };

const NOTES = [
  ["private", "How it runs", "Private processing", "Parsing, matching and the risk review run on your machine or in your trusted environment, with a local model."],
  ["retrieval", "How it runs", "A separate public worker", "Public pages are fetched by a separate process that receives source IDs and URLs, never your files."],
  ["ledger", "Controls", "The outbound ledger", "Every outbound request is recorded with its destination and purpose, so you can see what left and why."],
  ["stored", "Data", "What Tracefold stores", "IDs, hashes, file locations and sanitized text. Secret values are masked and never stored."],
  ["actions", "Controls", "Approval before action", "Takedown requests and key disables are drafted, then wait for a named person to approve them."],
  ["limits", "Limits", "Where the answers stop", "No match means no match in the sources checked. The details, stated plainly."],
];

const DETAIL: Record<string, [string, string][]> = {
  private: [
    ["Where scanning happens", "In the Tracefold engine, on your machine or in your trusted environment. The model is an Ollama model, and its endpoint has to be on the same machine."],
    ["Coding assistants", "Results returned to a cloud-backed coding assistant go to that assistant's model provider. Give it minimal disclosure: no paths, explanations or evidence text. Finding titles, rule IDs and coverage still reach it."],
  ],
  retrieval: [
    ["What the worker receives", "Source IDs, the approved URLs and which provider to use: Exa, Tavily or a direct fetch. It has no access to your files or to the model."],
    ["What it doesn't do", "It never searches with text from your files. On macOS it runs sandboxed away from the data directory and your workspace folders."],
  ],
  ledger: [
    ["What is recorded", "Each outbound request a scan made, with its destination, purpose and timing. Authentication is masked."],
    ["What it isn't", "A record, not proof of privacy on its own. A strict-private setup still needs a test showing the private side can't reach the network."],
  ],
  stored: [
    ["Private files", "Uploaded files stay in memory, expire after 15 minutes and are dropped on restart. They aren't written to disk."],
    ["Findings and evidence", "IDs, hashes, file locations and sanitized text. Secret values are masked in evidence and never stored, and model text is scrubbed of secrets before it's saved."],
  ],
  actions: [
    ["Takedown requests", "Drafted for every public match. Once a named, authorized person approves, it's emailed to the host's abuse or legal contact, or prefilled for the host's own form. Letters never include your private file's name or other private text."],
    ["Disabling AWS keys", "Drafted for leaked AWS access keys. On approval, Tracefold sets the key Inactive in IAM using your company's own remediation credentials. It never uses the leaked key and doesn't create a replacement."],
  ],
  limits: [
    ["What a result means", "Matching content found publicly, or no match in the N sources checked. Tracefold finds exact passages, not edited or paraphrased copies, and can't show that a copy doesn't exist elsewhere."],
    ["Submitted isn't removed", "A submitted takedown may still be online. Removal only shows after a fresh scan no longer finds the text at that URL. A recheck reports still detected, not detected in the checked version, or inconclusive."],
  ],
};

const RECORD = [
  ["28.65M", "new hardcoded secrets added to public GitHub commits in 2025.", "https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026/"],
  ["64%", "of valid secrets from 2022 still not revoked in 2026.", "https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026-pr/"],
  ["~28%", "of incidents starting in collaboration and productivity tools, not repositories.", "https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026-pr/"],
  ["38 TB", "of private data exposed by a single over-permissive token published on GitHub.", "https://www.wiz.io/blog/38-terabytes-of-private-data-accidentally-exposed-by-microsoft-ai-researchers"],
];

export default function Security() {
  return (
    <div className="bg-bg">
      <SiteHeader />

      {/* Intro */}
      <section className={cx("pb-[clamp(56px,6vw,88px)] pt-[clamp(140px,16vw,200px)]", EDGE)}>
        <div className="mx-auto max-w-[1760px]">
          <h1 className="rise text-[clamp(44px,6vw,88px)] font-semibold leading-[1] tracking-[-0.05em] text-white">Security at Tracefold.</h1>
          <p className="rise mt-6 max-w-[42rem] text-[clamp(17px,1.4vw,20px)] leading-[1.55] text-[#c2c3c7]" style={{ animationDelay: "100ms" }}>
            How Tracefold keeps your files on your side of the check, what it records, and where its answers stop.
          </p>
        </div>
      </section>

      {/* Notes rail */}
      <section className="pb-[clamp(72px,8vw,112px)]">
        <Carousel heading={<h2 className={cx(H2, "text-ink")}>The security model.</h2>}>
          {NOTES.map(([id, tag, t, d]) => (
            <CarouselItem key={id}>
              <a href={`#${id}`} className="group flex h-full flex-col overflow-hidden rounded-[24px] border border-line bg-[#090a0c] transition-colors hover:border-line-strong">
                <ImageSlot label="Note art: tracing paper over a printed page" className="h-[180px]" />
                <div className="flex flex-1 flex-col p-7">
                  <p className="text-xs text-faint">{tag}</p>
                  <h3 className="mt-2 text-[21px] font-medium leading-tight tracking-[-0.025em] text-ink">{t}</h3>
                  <p className="mt-3 flex-1 text-[15px] leading-[1.6] text-mute">{d}</p>
                  <span className="mt-6 inline-flex items-center gap-1.5 text-sm text-ink group-hover:underline group-hover:underline-offset-4">
                    Read <ArrowRight className="size-4" aria-hidden />
                  </span>
                </div>
              </a>
            </CarouselItem>
          ))}
        </Carousel>
      </section>

      {/* Details */}
      <section className={cx("pb-[clamp(72px,8vw,112px)]", EDGE)}>
        <div className="mx-auto max-w-[1400px] divide-y divide-line border-y border-line">
          {NOTES.map(([id, , t]) => (
            <div key={id} id={id} className="grid scroll-mt-28 gap-6 py-12 lg:grid-cols-[1fr_2fr] lg:gap-16">
              <h2 className="text-[clamp(24px,2.2vw,30px)] font-medium leading-tight tracking-[-0.03em] text-ink">{t}</h2>
              <dl className="grid gap-8 sm:grid-cols-2">
                {DETAIL[id].map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-[16px] font-medium tracking-[-0.01em] text-ink">{k}</dt>
                    <dd className="mt-2 text-[15px] leading-[1.65] text-mute">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </section>

      {/* Public record */}
      <section className={cx("pb-[clamp(72px,8vw,112px)]", EDGE)}>
        <div className="mx-auto max-w-[1400px]">
          <Reveal>
            <h2 className={cx(H2, "text-ink")}>Why checking for public copies matters.</h2>
            <p className="mt-4 max-w-2xl text-base leading-[1.6] text-mute">Published research on how often secrets and internal data end up public, and how long they stay there.</p>
          </Reveal>
          <ul className="mt-10 divide-y divide-line border-y border-line">
            {RECORD.map(([n, d, href]) => (
              <li key={n}>
                <a href={href} target="_blank" rel="noreferrer" className="group grid items-baseline gap-2 py-6 sm:grid-cols-[160px_1fr_auto] sm:gap-8">
                  <span className="text-[clamp(26px,2.4vw,34px)] font-medium tracking-[-0.04em] text-ink">{n}</span>
                  <span className="text-[16px] leading-[1.55] text-ink-2">{d}</span>
                  <ArrowUpRight className="hidden size-4 text-faint transition-colors group-hover:text-ink sm:block" aria-hidden />
                </a>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Work with us */}
      <section className={cx("pb-[clamp(80px,9vw,128px)]", EDGE)}>
        <Reveal className="mx-auto max-w-[1400px]">
          <div className="flex flex-wrap items-end justify-between gap-8 rounded-[24px] border border-line bg-[#111216] px-[clamp(24px,4vw,56px)] py-12">
            <div className="max-w-2xl">
              <h2 className="text-[clamp(26px,2.6vw,36px)] font-medium tracking-[-0.035em] text-ink">Found a security issue?</h2>
              <p className="mt-3 text-[16px] leading-[1.6] text-mute">
                Send us the details with steps to reproduce. Please don&apos;t test against other people&apos;s deployments or use any credentials you come
                across.
              </p>
            </div>
            <LinkButton href="/contact?topic=security" variant="secondary">
              Contact security <ArrowRight className="size-4" aria-hidden />
            </LinkButton>
          </div>
        </Reveal>
      </section>

      <SiteFooter />
    </div>
  );
}
