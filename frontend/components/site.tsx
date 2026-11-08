"use client";

// Marketing-site pieces: fixed floating header, scroll reveal, closing section, footer.
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import { ImageSlot, LinkButton, Wordmark, cx } from "./ui";
import { DotField } from "./dot-field";

export function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 24);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  // At the top the bar spans the page edge to edge; once scrolled it lifts into a floating,
  // bordered bar. Geometry, border and fill all move on one curve.
  return (
    <header
      className={cx(
        "fixed z-50 isolate border transition-[top,left,right,border-radius,border-color,box-shadow] duration-[720ms] ease-[cubic-bezier(.22,1,.36,1)]",
        "before:absolute before:inset-0 before:-z-10 before:rounded-[inherit] before:bg-[#090a0c]/90 before:backdrop-blur-xl before:transition-opacity before:duration-300",
        scrolled
          ? "left-[max(12px,calc(50%-700px))] right-[max(12px,calc(50%-700px))] top-3 rounded-2xl border-[rgb(255_255_255/0.11)] shadow-[inset_0_1px_0_rgb(255_255_255/0.02)] before:opacity-100"
          : "left-0 right-0 top-0 rounded-none border-transparent before:opacity-0",
      )}
    >
      <div
        className={cx(
          "flex items-center justify-between transition-[min-height,padding] duration-[720ms] ease-[cubic-bezier(.22,1,.36,1)]",
          scrolled ? "min-h-16 py-3 pl-6 pr-3" : "min-h-[84px] px-[max(20px,4vw)] py-5",
        )}
      >
        <Link href="/" aria-label="Tracefold home">
          <Wordmark className="text-[15px]" />
        </Link>
        <nav className="flex items-center gap-1">
          <LinkButton href="/overview">Dashboard</LinkButton>
        </nav>
      </div>
    </header>
  );
}

/** Slides content up 32px as it enters the viewport (0.72s, cubic-bezier(.2,.7,.2,1)). Visible without JS. */
export function Reveal({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"idle" | "pending" | "visible">("idle");
  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (el.getBoundingClientRect().top < window.innerHeight * 0.92) return;
    setState("pending");
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setState("visible");
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -8% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: state === "pending" ? 0 : 1,
        transform: state === "pending" ? "translateY(32px)" : "none",
        transition:
          state === "visible" ? `opacity .72s cubic-bezier(.2,.7,.2,1) ${delay}ms, transform .72s cubic-bezier(.2,.7,.2,1) ${delay}ms` : undefined,
      }}
    >
      {children}
    </div>
  );
}

/** Closing call to action: muted-then-bright headline beside a lens card. */
export function Mission() {
  return (
    <section className="px-[max(32px,4vw)] pb-[88px] pt-10">
      <div className="mx-auto grid max-w-[1760px] grid-cols-1 items-center gap-12 lg:grid-cols-[1.85fr_1fr] [&>*]:min-w-0">
        <Reveal className="py-4">
          <h2 className="max-w-[22ch] text-[clamp(32px,3vw,44px)] leading-[1.12] tracking-[-0.045em]">
            <span className="block text-mute">Your team writes code and docs every day.</span>
            <span className="block text-ink">Tracefold checks whether any of it is already public.</span>
          </h2>
          <div className="mt-8 flex flex-wrap gap-3">
            <LinkButton href="/scan">
              Get started <ArrowRight className="size-4" aria-hidden />
            </LinkButton>
          </div>
        </Reveal>

        <Reveal delay={120}>
          <ImageSlot label="Closing art" src="/preview/pointillist-hero.webp" position="35% center" className="flex aspect-[446/398] items-end justify-center rounded-[24px] border border-line pb-[9%]">
            <LinkButton href="/scan">Run your first check</LinkButton>
          </ImageSlot>
        </Reveal>
      </div>
    </section>
  );
}

const FOOTER_NAV = [
  {
    title: "Product",
    links: [
      ["How it works", "/#how"],
      ["Dashboard", "/overview"],
    ],
  },
];


export function SiteFooter() {
  return (
    <footer className="bg-[#090a0c]">
      <div className="mx-auto max-w-[1760px] px-[max(32px,4vw)] pb-6 pt-14">
        <div className="flex flex-col gap-12 xl:flex-row xl:justify-between">
          <div className="min-w-0 xl:max-w-[300px]">
            <Link href="/" aria-label="Tracefold home" className="inline-flex py-1">
              <Wordmark className="text-[15px]" />
            </Link>
            <p className="mt-3 text-sm leading-relaxed text-[#92959c]">
              Finds company documents and code on public pages, and flags risks in your own files.
              <br />
              Runs on your machine or in your trusted environment.
            </p>
          </div>
          <nav className="flex flex-wrap gap-x-16 gap-y-10" aria-label="Footer">
            {FOOTER_NAV.map((g) => (
              <div key={g.title}>
                <h2 className="text-[17px] font-semibold tracking-[-0.015em] text-ink">{g.title}</h2>
                <ul className="mt-3 space-y-1 text-sm text-[#92959c]">
                  {g.links.map(([label, href]) => (
                    <li key={label}>
                      <Link href={href} className="inline-block py-1 transition-colors duration-150 hover:text-ink">
                        {label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </div>

        {/* Printed strip over a drifting halftone field */}
        <DotField className="mt-12 py-8">
          <div className="flex items-center justify-between gap-10">
            <p className="min-w-0 flex-1 text-[clamp(26px,4.6vw,64px)] font-semibold leading-[1.05] tracking-[-0.055em] text-ink">
              <span className="inline-block whitespace-nowrap">Match / Review /</span> <span className="inline-block whitespace-nowrap">Approve / Recheck</span>
            </p>
            <Wordmark className="hidden shrink-0 text-[clamp(13px,1.35vw,19px)] sm:inline-flex" />
          </div>
        </DotField>

        <div className="flex flex-wrap justify-between gap-4 pt-10 text-xs text-[#92959c]">
          <span>© 2026 Tracefold</span>
        </div>
      </div>
    </footer>
  );
}
