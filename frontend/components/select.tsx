"use client";

// Custom select: a button that opens a listbox. Keyboard: ↑/↓ move, Home/End, Enter/Space pick,
// Esc closes, typing jumps to the first match. Closes on outside click. The list renders in a
// portal with fixed positioning so containers with overflow:hidden can't clip it.
import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { cx } from "./ui";

export interface Option<T extends string> {
  value: T;
  label: string;
  icon?: ReactNode;
}

export function Select<T extends string>({
  value,
  onChange,
  options,
  label,
  size = "sm",
  className,
  disabled,
  align = "start",
}: {
  value: T;
  onChange: (v: T) => void;
  options: Option<T>[];
  label: string; // accessible name
  size?: "sm" | "md";
  className?: string;
  disabled?: boolean;
  align?: "start" | "end";
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const typed = useRef({ text: "", at: 0 });
  const [pos, setPos] = useState<{ x: number; y: number; minWidth: number; up: boolean } | null>(null);
  const id = useId();
  const current = options.find((o) => o.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!root.current?.contains(t) && !list.current?.contains(t)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const r = button.current?.getBoundingClientRect();
      if (!r) return;
      const height = Math.min(288, options.length * 32 + 10);
      const up = r.bottom + 6 + height > window.innerHeight && r.top - 6 - height > 0;
      setPos({
        x: align === "end" ? window.innerWidth - r.right : r.left,
        y: up ? window.innerHeight - r.top + 6 : r.bottom + 6,
        minWidth: r.width,
        up,
      });
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, align, options.length]);

  useEffect(() => {
    if (open) list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  function show() {
    setActive(Math.max(0, options.findIndex((o) => o.value === value)));
    setOpen(true);
    requestAnimationFrame(() => list.current?.focus());
  }

  function pick(i: number) {
    const o = options[i];
    if (o) onChange(o.value);
    setOpen(false);
    button.current?.focus();
  }

  function onListKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") setActive((a) => Math.min(options.length - 1, a + 1));
    else if (e.key === "ArrowUp") setActive((a) => Math.max(0, a - 1));
    else if (e.key === "Home") setActive(0);
    else if (e.key === "End") setActive(options.length - 1);
    else if (e.key === "Enter" || e.key === " ") pick(active);
    else if (e.key === "Escape" || e.key === "Tab") {
      setOpen(false);
      if (e.key === "Escape") button.current?.focus();
      return;
    } else if (e.key.length === 1) {
      const now = Date.now();
      typed.current.text = (now - typed.current.at < 600 ? typed.current.text : "") + e.key.toLowerCase();
      typed.current.at = now;
      const i = options.findIndex((o) => o.label.toLowerCase().startsWith(typed.current.text));
      if (i >= 0) setActive(i);
      return;
    } else return;
    e.preventDefault();
  }

  return (
    <div ref={root} className={cx("relative inline-block", className)}>
      <button
        ref={button}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${label}: ${current?.label}`}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            show();
          }
        }}
        className={cx(
          "inline-flex w-full items-center justify-between gap-2 rounded-ctl border bg-panel-2 text-ink transition-colors duration-150",
          "disabled:pointer-events-none disabled:opacity-50",
          open ? "border-line-strong bg-raised" : "border-[rgb(255_255_255/0.14)] hover:border-line-strong",
          size === "sm" ? "h-8 pl-3 pr-2 text-[13px]" : "h-10 pl-3.5 pr-2.5 text-sm",
        )}
      >
        <span className="flex min-w-0 items-center gap-2 truncate">
          {current?.icon}
          {current?.label}
        </span>
        <ChevronDown className={cx("size-3.5 shrink-0 text-faint transition-transform duration-200", open && "rotate-180")} aria-hidden />
      </button>

      {open &&
        pos &&
        createPortal(
        <ul
          ref={list}
          id={id}
          role="listbox"
          tabIndex={-1}
          aria-label={label}
          aria-activedescendant={`${id}-${active}`}
          onKeyDown={onListKey}
          className={cx(
            "scroll-thin fixed z-[100] max-h-72 overflow-auto rounded-ctl border border-line-strong bg-[#1a1a1a] p-1 shadow-[0_16px_40px_-8px_rgb(0_0_0/0.7)] outline-none",
            "animate-[menu-in_140ms_cubic-bezier(.16,1,.3,1)]",
            pos.up ? "origin-bottom" : "origin-top",
          )}
          style={{
            [align === "end" ? "right" : "left"]: pos.x,
            [pos.up ? "bottom" : "top"]: pos.y,
            minWidth: pos.minWidth,
          }}
        >
          {options.map((o, i) => {
            const selected = o.value === value;
            return (
              <li
                key={o.value}
                id={`${id}-${i}`}
                data-index={i}
                role="option"
                aria-selected={selected}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(i)}
                className={cx(
                  "flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-[7px] py-1.5 pl-2.5 pr-8 text-[13px] transition-colors duration-100",
                  "relative",
                  i === active ? "bg-raised text-ink" : "text-ink-2",
                )}
              >
                {o.icon}
                {o.label}
                {selected && <Check className="absolute right-2 size-3.5 text-ink" aria-hidden />}
              </li>
            );
          })}
        </ul>,
        document.body,
        )}
    </div>
  );
}
