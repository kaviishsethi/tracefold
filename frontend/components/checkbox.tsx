"use client";

// Themed checkbox. The real input stays in the DOM (visually hidden) so labels, keyboard and forms keep working.
import { Check } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "./ui";

export function Checkbox({
  checked,
  onChange,
  disabled,
  children,
  className,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx("group inline-flex items-start gap-2.5 text-sm text-ink-2", disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer", className)}>
      <input type="checkbox" className="peer sr-only" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span
        aria-hidden
        className={cx(
          "mt-[3px] flex size-4 shrink-0 items-center justify-center rounded-[5px] border transition-colors duration-150",
          "peer-focus-visible:ring-2 peer-focus-visible:ring-accent/50 peer-focus-visible:ring-offset-1 peer-focus-visible:ring-offset-bg",
          checked ? "border-accent bg-accent" : "border-line-strong bg-panel-2 group-hover:border-mute",
        )}
      >
        <Check className={cx("size-3 text-[#0a0c0c] transition-opacity", checked ? "opacity-100" : "opacity-0")} strokeWidth={3} />
      </span>
      {children && <span className="min-w-0">{children}</span>}
    </label>
  );
}
