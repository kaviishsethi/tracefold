"use client";

// Pricing tiers with an annual / monthly toggle. Every plan runs the same scan engine in the
// customer's own environment; price points carried over unchanged from the earlier design.
import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import { Reveal } from "./site";
import { ImageSlot, LinkButton, cx } from "./ui";

type Billing = "annual" | "monthly";

const TIERS = [
  {
    name: "Starter",
    badge: "No card required",
    price: { annual: "Free", monthly: "Free" },
    unit: "",
    note: { annual: "Free forever", monthly: "Free forever" },
    cta: { label: "Get started", href: "/setup" },
    key: ["Upload platform and MCP integration", "Local model review with Ollama", "Community support"],
    included: [
      "Exact passage matching against public sources you approve",
      "Evidence with your file, lines, public URL and retrieval time",
      "Potential risks in your files, with suggested changes",
      "Rechecks after you edit a file",
      "Outbound request ledger",
    ],
  },
  {
    name: "Team",
    badge: "Most teams",
    price: { annual: "$199", monthly: "$239" },
    unit: "/ month",
    note: { annual: "Billed annually at $2,388", monthly: "Billed monthly" },
    cta: { label: "Start with Team", href: "/setup" },
    key: ["Takedown requests and AWS key actions", "Approval by named, authorized people", "Email support, 1 business day"],
    included: [
      "Everything in Starter",
      "A takedown request drafted for every public match",
      "Disable-key actions for leaked AWS access keys",
      "Review states, with a required reason to dismiss",
      "Minimal-disclosure access for cloud-backed assistants",
    ],
    featured: true,
  },
  {
    name: "Enterprise",
    badge: "Your environment",
    price: { annual: "Custom", monthly: "Custom" },
    unit: "",
    note: { annual: "From $1,500 / month, billed annually", monthly: "From $1,500 / month, billed annually" },
    cta: { label: "Talk to us", href: "/contact?topic=enterprise" },
    key: ["Multiple workspaces", "Strict-private setup with a local-model assistant", "Dedicated support with an SLA"],
    included: [
      "Everything in Team",
      "Runs inside your own network or private cloud",
      "Managed setup and security review",
      "Help setting up public sources and takedown contacts",
    ],
  },
];

export function PricingPlans() {
  const [billing, setBilling] = useState<Billing>("annual");
  return (
    <div>
      <div className="mb-10 flex flex-wrap items-end justify-between gap-6">
        <div>
          <h2 className="text-[clamp(36px,4vw,56px)] font-medium leading-[1.05] tracking-[-0.045em] text-ink">Pricing</h2>
          <p className="mt-3 text-[16px] text-mute">For startups, security teams and enterprises.</p>
        </div>
        <div role="radiogroup" aria-label="Billing period" className="inline-flex rounded-ctl border border-line bg-panel-2 p-1 text-[13px]">
          {(["annual", "monthly"] as const).map((b) => (
            <button
              key={b}
              role="radio"
              aria-checked={billing === b}
              onClick={() => setBilling(b)}
              className={cx(
                "inline-flex h-8 items-center gap-2 rounded-[7px] px-4 font-medium transition-colors duration-150",
                billing === b ? "bg-raised text-ink shadow-[0_1px_2px_rgb(0_0_0/0.4)]" : "text-mute hover:text-ink",
              )}
            >
              {b === "annual" ? "Annual" : "Monthly"}
              {b === "annual" && <span className="rounded bg-accent/15 px-1.5 text-[11px] text-accent">2 months free</span>}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {TIERS.map((t, i) => (
          <Reveal key={t.name} delay={i * 80} className="h-full">
            <article
              className={cx(
                "relative isolate flex h-full flex-col overflow-hidden rounded-[24px] border",
                t.featured ? "border-accent/40" : "border-line",
              )}
            >
              {/* art header, like the plan cards' image tops */}
              <ImageSlot label="Plan art: folded tracing paper, close up" className="absolute inset-x-0 top-0 -z-10 h-[220px] opacity-80" />
              <div aria-hidden className="absolute inset-x-0 top-0 -z-10 h-[220px] bg-[linear-gradient(180deg,transparent_10%,#090a0c_92%)]" />
              <div className="absolute inset-x-0 bottom-0 top-[220px] -z-10 bg-[#090a0c]" />

              <div className="flex flex-1 flex-col p-8">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-[22px] font-medium tracking-[-0.025em] text-ink">{t.name}</h3>
                  <span className={cx("rounded-md border px-2 py-0.5 text-xs", t.featured ? "border-accent/40 bg-accent/10 text-accent" : "border-white/15 bg-black/30 text-ink-2")}>
                    {t.badge}
                  </span>
                </div>
                <p className="mt-10 flex items-baseline gap-2">
                  <span className="text-[clamp(44px,4vw,60px)] font-medium leading-none tracking-[-0.05em] text-white tabular-nums">{t.price[billing]}</span>
                  {t.unit && <span className="text-[15px] text-mute">{t.unit}</span>}
                </p>
                <p className="mt-2 text-[13px] text-mute">{t.note[billing]}</p>

                <div className="mt-7 flex items-center gap-4">
                  <LinkButton href={t.cta.href} variant={t.featured ? "primary" : "secondary"}>
                    {t.cta.label} <ArrowRight className="size-4" aria-hidden />
                  </LinkButton>
                  <Link href="/enterprise#how" className="text-sm text-mute underline-offset-4 hover:text-ink hover:underline">
                    How it works
                  </Link>
                </div>

                <ul className="mt-8 space-y-2.5 text-[15px] text-ink">
                  {t.key.map((k) => (
                    <li key={k} className="flex gap-3">
                      <Check className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
                      {k}
                    </li>
                  ))}
                </ul>
                <div className="mt-8 border-t border-line pt-6">
                  <p className="mb-3 text-xs text-faint">Included</p>
                  <ul className="space-y-2 text-[14px] text-mute">
                    {t.included.map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </article>
          </Reveal>
        ))}
      </div>
    </div>
  );
}
