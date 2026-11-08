"use client";

// Orange halftone field behind a section. Two dot layers drift slowly in opposite phases, masked
// from opposite sides; a brighter layer fades in around the pointer and eases after it.
// Pauses off-screen and when the tab is hidden; static under prefers-reduced-motion.
import { useEffect, useRef, type ReactNode } from "react";
import { cx } from "./ui";

export function DotField({ children, className }: { children: ReactNode; className?: string }) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let x = 0,
      y = 0,
      tx = 0,
      ty = 0,
      raf = 0,
      visible = false;
    const tick = () => {
      x += (tx - x) * 0.12;
      y += (ty - y) * 0.12;
      el.style.setProperty("--dot-x", `${x}px`);
      el.style.setProperty("--dot-y", `${y}px`);
      raf = Math.abs(tx - x) + Math.abs(ty - y) > 0.3 ? requestAnimationFrame(tick) : 0;
    };
    const move = (e: PointerEvent) => {
      if (reduced.matches || e.pointerType === "touch") return;
      const r = el.getBoundingClientRect();
      tx = e.clientX - r.left;
      ty = e.clientY - r.top;
      if (!el.hasAttribute("data-hover")) {
        x = tx;
        y = ty;
      }
      el.setAttribute("data-hover", "");
      if (!raf) raf = requestAnimationFrame(tick);
    };
    const leave = () => el.removeAttribute("data-hover");
    const sync = () => el.toggleAttribute("data-paused", !visible || document.hidden || reduced.matches);
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      sync();
    });
    io.observe(el);
    el.addEventListener("pointermove", move, { passive: true });
    el.addEventListener("pointerleave", leave);
    document.addEventListener("visibilitychange", sync);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
      document.removeEventListener("visibilitychange", sync);
    };
  }, []);

  return (
    <div ref={root} className={cx("dot-field relative isolate", className)}>
      <div aria-hidden className="dot-field__atmosphere">
        <i />
        <i />
        <b />
      </div>
      {children}
    </div>
  );
}
