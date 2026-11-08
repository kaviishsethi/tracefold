import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Accordion } from "@/components/accordion";
import { EDGE } from "@/components/marketing";
import { PricingPlans } from "@/components/pricing-plans";
import { Reveal, SiteFooter, SiteHeader } from "@/components/site";
import { ImageSlot, LinkButton, cx } from "@/components/ui";

export const metadata = { title: "Pricing · Tracefold" };

const VALUES = [
  ["Runs in your environment on every plan", "The scan engine and local model run on your machine or in your trusted environment, from the free tier up."],
  ["Upload and MCP on every plan", "Check existing documents in the web app, and check changes as you work through your coding assistant."],
  ["No seat fees", "Add your whole security team. Plans aren't priced per person."],
];

const HELP = [
  ["Your deployment requirements", "Your own network, private cloud or several environments, with managed setup and an SLA.", "Explore enterprise", "/enterprise"],
  ["Planning a security review?", "See what Tracefold sends out, what it stores, and where its answers stop.", "Read the security model", "/security"],
  ["Help with your first scan", "Get help starting the engine, choosing public sources and connecting your coding assistant.", "Request an onboarding call", "/contact?topic=support"],
];

const FAQ: [string, string][] = [
  [
    "What's included on the free plan?",
    "The upload platform, the MCP integration, matching against public sources you approve, the review of risks in your files, rechecks and the outbound ledger.",
  ],
  [
    "Do you ever see our documents?",
    "Not in the recommended setup. The scan engine and model run on your machine or in your trusted environment, and the worker that fetches public pages never receives your files. A cloud-backed coding assistant receives whatever findings its access allows, so give it minimal disclosure.",
  ],
  [
    "Does Tracefold send takedown requests on its own?",
    "No. It drafts them. A named, authorized person approves each one before it's emailed to the host or prefilled for the host's own form. Submitted isn't removed: removal only shows after a fresh scan no longer finds the text.",
  ],
  ["How does annual billing work?", "Annual plans are billed once a year at ten times the monthly price, so you get two months free."],
  ["Can we start free and upgrade later?", "Yes. Your findings and ledger stay where they are when you change plans."],
];

export default function Pricing() {
  return (
    <div className="bg-bg">
      <SiteHeader />

      {/* Hero card */}
      <section className={cx("pt-[104px]", EDGE)}>
        <div className="mx-auto max-w-[1760px]">
          <ImageSlot label="Pricing hero art: sheets of tracing paper stacked over printed pages" className="flex min-h-[460px] items-end rounded-[28px] border border-line">
            <div className="grid w-full items-end gap-10 p-[clamp(28px,4vw,56px)] lg:grid-cols-[1.3fr_1fr]">
              <div>
                <h1 className="rise max-w-[14ch] text-[clamp(40px,5vw,72px)] font-semibold leading-[1.02] tracking-[-0.045em] text-white">
                  Public-exposure checks for every team.
                </h1>
                <p className="rise mt-6 max-w-[34rem] text-[clamp(16px,1.3vw,19px)] leading-[1.55] text-[#c2c3c7]" style={{ animationDelay: "100ms" }}>
                  Most security tools charge per seat and keep their pricing behind a sales call. Tracefold lists its plans here, and every plan runs the
                  same scan engine in your own environment.
                </p>
                <div className="rise mt-8 flex flex-wrap items-center gap-4" style={{ animationDelay: "200ms" }}>
                  <LinkButton href="/scan">
                    Get started <ArrowRight className="size-4" aria-hidden />
                  </LinkButton>
                  <span className="text-sm text-mute">Starter is free. No card required.</span>
                </div>
              </div>
              <p className="rise hidden text-right text-[clamp(22px,2vw,30px)] font-medium leading-[1.2] tracking-[-0.03em] text-white/60 lg:block" style={{ animationDelay: "300ms" }}>
                Same engine on every plan.
                <br />
                No seat fees.
              </p>
            </div>
          </ImageSlot>
        </div>
      </section>

      {/* Plans */}
      <section className={cx("py-[clamp(72px,8vw,112px)]", EDGE)}>
        <div className="mx-auto max-w-[1760px]">
          <PricingPlans />
        </div>
      </section>

      {/* Values */}
      <section className={cx("pb-[clamp(72px,8vw,112px)]", EDGE)}>
        <div className="mx-auto max-w-[1760px] border-t border-line pt-12">
          <div className="grid gap-10 lg:grid-cols-[1fr_3fr]">
            <h2 className="text-[clamp(26px,2.4vw,34px)] font-medium leading-tight tracking-[-0.035em] text-ink">Pricing you can read.</h2>
            <div className="grid gap-8 sm:grid-cols-3">
              {VALUES.map(([t, d]) => (
                <Reveal key={t}>
                  <p className="text-[17px] font-medium tracking-[-0.02em] text-ink">{t}</p>
                  <p className="mt-2 text-[15px] leading-[1.6] text-mute">{d}</p>
                </Reveal>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Help */}
      <section className={cx("pb-[clamp(72px,8vw,112px)]", EDGE)}>
        <div className="mx-auto grid max-w-[1760px] gap-4 md:grid-cols-3">
          {HELP.map(([t, d, cta, href], i) => (
            <Reveal key={t} delay={i * 80} className="h-full">
              <article className="flex h-full flex-col rounded-[24px] border border-line bg-[#090a0c] p-7">
                <h2 className="text-[21px] font-medium leading-tight tracking-[-0.025em] text-ink">{t}</h2>
                <p className="mt-3 flex-1 text-[15px] leading-[1.6] text-mute">{d}</p>
                <Link href={href} className="mt-6 inline-flex items-center gap-1.5 text-[15px] text-ink hover:underline hover:underline-offset-4">
                  {cta} <ArrowRight className="size-4" aria-hidden />
                </Link>
              </article>
            </Reveal>
          ))}
        </div>
      </section>

      {/* FAQ */}
      <section className={cx("pb-[clamp(80px,9vw,130px)]", EDGE)}>
        <div className="mx-auto grid max-w-[1760px] gap-10 lg:grid-cols-[1fr_2fr]">
          <h2 className="text-[clamp(30px,3vw,44px)] font-medium leading-[1.1] tracking-[-0.04em] text-ink">Frequently asked questions</h2>
          <Accordion items={FAQ} />
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
