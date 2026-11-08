"use client";

// Motion primitives for the marketing site: cloud section transition, snap carousel, ticker.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { cx } from "./ui";

const smoother = (v: number) => {
  const p = Math.max(0, Math.min(1, v));
  return p * p * p * (p * (p * 6 - 15) + 10);
};

/**
 * Fog-like edge between the dark page and a paper section. A tall gradient whose boundary
 * rolls in broad, slow waves, dithered with fixed grain. The wave term is weighted by
 * sin²(πy) so the top stays fully transparent and the bottom fully paper: no visible seam.
 * Static under prefers-reduced-motion; animates (~30fps) only while on screen.
 */
export function CloudTransition({ reverse = false, height = 400 }: { reverse?: boolean; height?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let W = 0,
      H = 0,
      img: ImageData | null = null,
      grain: Float32Array | null = null,
      raf = 0,
      visible = false,
      last = 0;
    const start = performance.now();

    const resize = () => {
      const box = canvas.getBoundingClientRect();
      W = Math.max(1, Math.round(Math.min(box.width, 900)));
      H = Math.max(1, Math.round((box.height * W) / Math.max(1, box.width)));
      canvas.width = W;
      canvas.height = H;
      img = ctx.createImageData(W, H);
      grain = new Float32Array(W * H);
      let seed = 1234567;
      for (let i = 0; i < grain.length; i++) {
        seed = (seed * 48271) % 2147483647;
        grain[i] = (seed / 2147483647 - 0.5) * 0.05;
        img.data[i * 4] = 247;
        img.data[i * 4 + 1] = 245;
        img.data[i * 4 + 2] = 242;
      }
      draw(performance.now());
    };

    const draw = (now: number) => {
      if (!img || !grain) return;
      const t = (now - start) / 2800;
      const wave = new Float32Array(W);
      for (let x = 0; x < W; x++) {
        const u = x / W;
        wave[x] = 0.16 * Math.sin(u * 5.3 + t + 0.6) + 0.07 * Math.cos(u * 11.7 - t * 0.8) + 0.03 * Math.sin(u * 23 + t * 0.5);
      }
      for (let y = 0; y < H; y++) {
        const v0 = y / Math.max(1, H - 1);
        const v = reverse ? 1 - v0 : v0;
        const env = Math.sin(v * Math.PI) ** 2;
        for (let x = 0; x < W; x++) {
          const i = y * W + x;
          img.data[i * 4 + 3] = Math.round(255 * smoother((v - 0.05) / 0.9 + wave[x] * env + grain[i] * env));
        }
      }
      ctx.putImageData(img, 0, 0);
    };

    const loop = (now: number) => {
      if (now - last > 33) {
        draw(now);
        last = now;
      }
      if (visible) raf = requestAnimationFrame(loop);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting && !still;
      cancelAnimationFrame(raf);
      if (visible) raf = requestAnimationFrame(loop);
    });
    io.observe(canvas);
    return () => {
      ro.disconnect();
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [reverse]);

  return (
    <div
      aria-hidden
      className={cx("relative z-[1] w-full overflow-hidden", reverse ? "-mt-0.5" : "-mb-0.5")}
      style={{ height, background: reverse ? "linear-gradient(#f3f6f5, transparent)" : "linear-gradient(transparent, #f3f6f5)" }}
    >
      <canvas ref={ref} className="absolute inset-0 h-full w-full bg-bg" />
    </div>
  );
}

/** Horizontal snap carousel with a heading and arrow controls (3 visible + a peek on desktop). */
export function Carousel({ heading, children, className }: { heading: ReactNode; children: ReactNode; className?: string }) {
  const track = useRef<HTMLDivElement>(null);
  const [edge, setEdge] = useState({ start: true, end: false });
  useEffect(() => {
    const el = track.current;
    if (!el) return;
    const on = () => setEdge({ start: el.scrollLeft < 8, end: el.scrollLeft + el.clientWidth > el.scrollWidth - 8 });
    on();
    el.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      el.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
    };
  }, []);
  const step = (dir: number) => {
    const el = track.current;
    if (!el) return;
    const card = el.querySelector<HTMLElement>("[data-carousel-item]");
    el.scrollBy({ left: dir * ((card?.offsetWidth ?? 400) + 20), behavior: "smooth" });
  };
  const arrow = "flex size-11 items-center justify-center rounded-ctl border border-line bg-panel-2 text-ink transition-colors duration-150 hover:bg-raised disabled:opacity-35";
  return (
    <div className={className}>
      <div className="mb-10 flex items-end justify-between gap-10 px-[max(32px,4vw)]">
        <div className="min-w-0 max-w-[1100px]">{heading}</div>
        <div className="hidden shrink-0 gap-2.5 pb-1 sm:flex">
          <button aria-label="Previous" className={arrow} disabled={edge.start} onClick={() => step(-1)}>
            <ArrowLeft className="size-4" aria-hidden />
          </button>
          <button aria-label="Next" className={arrow} disabled={edge.end} onClick={() => step(1)}>
            <ArrowRight className="size-4" aria-hidden />
          </button>
        </div>
      </div>
      <div
        ref={track}
        tabIndex={0}
        aria-label="Carousel"
        className="flex snap-x snap-mandatory scroll-px-[max(32px,4vw)] gap-5 overflow-x-auto px-[max(32px,4vw)] pb-2 outline-none [scrollbar-width:none] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent [&::-webkit-scrollbar]:hidden"
      >
        {children}
      </div>
    </div>
  );
}

export function CarouselItem({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      data-carousel-item
      className={cx("w-[max(300px,min(86vw,420px))] shrink-0 snap-start lg:w-[calc((100vw-max(32px,4vw)-100px-40px)/3)]", className)}
    >
      {children}
    </div>
  );
}

/** Endless ticker. Pauses on hover and under reduced motion. */
export function Ticker({ items }: { items: string[] }) {
  const row = (
    <ul className="flex shrink-0 items-center gap-10 pr-10" aria-hidden>
      {items.map((s) => (
        <li key={s} className="flex items-center gap-2 whitespace-nowrap font-mono text-[13px] text-mute">
          <span className="size-1 rounded-full bg-accent" />
          {s}
        </li>
      ))}
    </ul>
  );
  return (
    <div className="group relative overflow-hidden [mask-image:linear-gradient(90deg,transparent,black_8%,black_92%,transparent)]">
      <p className="sr-only">Detects {items.join(", ")} and more.</p>
      <div className="flex w-max animate-[ticker_60s_linear_infinite] group-hover:[animation-play-state:paused] motion-reduce:animate-none">
        {row}
        {row}
      </div>
    </div>
  );
}
