// Shared layout for the marketing pages (manifesto, enterprise, pricing, security, contact).
import type { ReactNode } from "react";
import { Reveal, SiteFooter, SiteHeader } from "./site";
import { cx } from "./ui";

export const EDGE = "px-[max(32px,4vw)]";
export const H2 = "text-[clamp(30px,3.2vw,44px)] leading-[1.14] tracking-[-0.035em]";

export function MarketingPage({ title, lead, children, aside }: { title: ReactNode; lead?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="bg-bg">
      <SiteHeader />
      <header className={cx("relative isolate overflow-hidden pb-[clamp(56px,7vw,96px)] pt-[clamp(140px,16vw,200px)]", EDGE)}>
        <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(70%_120%_at_80%_0%,rgb(79_184_166/0.10),transparent_60%)]" />
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-end justify-between gap-10">
          <div className="max-w-[56rem]">
            <h1 className="rise text-[clamp(40px,5vw,72px)] font-semibold leading-[1.02] tracking-[-0.045em] text-white">{title}</h1>
            {lead && (
              <p className="rise mt-6 max-w-[40rem] text-[clamp(17px,1.4vw,20px)] leading-[1.55] text-[#c2c3c7]" style={{ animationDelay: "100ms" }}>
                {lead}
              </p>
            )}
          </div>
          {aside && (
            <div className="rise" style={{ animationDelay: "200ms" }}>
              {aside}
            </div>
          )}
        </div>
      </header>
      {children}
      <SiteFooter />
    </div>
  );
}

export function Section({ children, className, title, lead }: { children: ReactNode; className?: string; title?: ReactNode; lead?: ReactNode }) {
  return (
    <section className={cx("pb-[clamp(72px,8vw,120px)]", EDGE, className)}>
      <div className="mx-auto max-w-[1400px]">
        {title && (
          <Reveal className="mb-10">
            <h2 className={cx(H2, "max-w-3xl text-ink")}>{title}</h2>
            {lead && <p className="mt-4 max-w-2xl text-base leading-[1.6] text-mute">{lead}</p>}
          </Reveal>
        )}
        {children}
      </div>
    </section>
  );
}

export function Card({ title, children, className }: { title: ReactNode; children: ReactNode; className?: string }) {
  return (
    <article className={cx("h-full rounded-[24px] border border-line bg-[#090a0c] p-7", className)}>
      <h3 className="text-[21px] leading-tight tracking-[-0.025em] text-ink">{title}</h3>
      <div className="mt-3 text-[15px] leading-[1.6] text-mute">{children}</div>
    </article>
  );
}
