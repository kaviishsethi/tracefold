// Shared UI primitives. Tokens live in app/globals.css.
import Link from "next/link";
import type { ReactNode } from "react";
import { ImageIcon, Loader2 } from "lucide-react";
import type { FindingStatus, Severity } from "@/lib/api";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANT: Record<Variant, string> = {
  primary: "bg-[#fafafa] text-[#0a0c0c] hover:bg-white",
  secondary: "border border-[#414846] bg-panel-2 text-ink hover:border-[#56605d] hover:bg-raised",
  ghost: "text-mute hover:bg-panel-2 hover:text-ink",
  danger: "border border-crit/30 bg-crit/10 text-crit hover:bg-crit/15",
};
const SIZE: Record<Size, string> = { sm: "h-8 px-3 text-[13px]", md: "h-10 px-4 text-sm", lg: "h-11 px-5 text-[15px]" };

function buttonClass(variant: Variant, size: Size, className?: string) {
  return cx(
    "inline-flex shrink-0 items-center justify-center gap-2 rounded-ctl font-medium whitespace-nowrap",
    "transition-[background-color,border-color,color,transform] duration-200 ease-out-expo active:translate-y-px",
    "disabled:pointer-events-none disabled:opacity-45",
    VARIANT[variant],
    SIZE[size],
    className,
  );
}

/** `loading` keeps the label in place (invisible) and centres a spinner over it, so the button never resizes. */
export function Button({
  variant = "primary",
  size = "md",
  className,
  loading = false,
  children,
  disabled,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean }) {
  return (
    <button {...props} disabled={disabled || loading} aria-busy={loading || undefined} className={cx(buttonClass(variant, size, className), "relative", loading && "disabled:opacity-100")}>
      <span className={cx("inline-flex items-center justify-center gap-2", loading && "invisible")}>{children}</span>
      {loading && (
        <span className="absolute inset-0 flex items-center justify-center">
          <Loader2 aria-hidden className="size-4 animate-spin" />
        </span>
      )}
    </button>
  );
}

export function LinkButton({
  href,
  children,
  variant = "primary",
  size = "md",
  className,
}: {
  href: string;
  children: ReactNode;
  variant?: Variant;
  size?: Size;
  className?: string;
}) {
  return (
    <Link href={href} className={buttonClass(variant, size, className)}>
      {children}
    </Link>
  );
}

/** A product window: rounded panel with a header strip. The main container on every app screen. */
export function Panel({
  title,
  meta,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("overflow-hidden rounded-card border border-line bg-panel shadow-[0_12px_32px_rgb(0_0_0/0.2)]", className)}>
      {(title || meta || actions) && (
        <header className="flex min-h-11 items-center justify-between gap-3 border-b border-line px-4 py-2">
          <div className="flex min-w-0 items-center gap-2.5">
            {title && <h2 className="truncate text-[13px] font-medium tracking-normal text-ink">{title}</h2>}
            {meta && <span className="truncate text-xs text-faint">{meta}</span>}
          </div>
          {actions}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

export const SEVERITY_STYLE: Record<Severity, { dot: string; text: string; label: string; bar: string }> = {
  high: { dot: "bg-crit", text: "text-crit", label: "High", bar: "bg-crit" },
  medium: { dot: "bg-med", text: "text-med", label: "Medium", bar: "bg-med" },
  low: { dot: "bg-low", text: "text-low", label: "Low", bar: "bg-low" },
};

export function SeverityBadge({ severity }: { severity: Severity | null | undefined }) {
  if (!severity) return <span className="text-[13px] text-faint">–</span>;
  const s = SEVERITY_STYLE[severity];
  return (
    <span className={cx("inline-flex items-center gap-2 text-[13px] font-medium", s.text)}>
      <span className={cx("size-1.5 rounded-full", s.dot)} />
      {s.label}
    </span>
  );
}

export const STATUS_LABEL: Record<FindingStatus, string> = {
  open: "Open",
  not_detected_in_checked_version: "Not detected in checked version",
  no_longer_observed: "No longer observed",
};

/** Finding status in the engine's words. Never "fixed" or "resolved". */
export function StatusPill({ status }: { status: FindingStatus }) {
  return (
    <span
      className={cx(
        "inline-flex h-6 items-center rounded-md border px-2 text-xs font-medium whitespace-nowrap",
        status === "open" && "border-line-strong bg-panel-2 text-ink",
        status === "not_detected_in_checked_version" && "border-local-line bg-local-bg text-local",
        status === "no_longer_observed" && "border-ok/25 bg-ok/10 text-ok",
      )}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[22px] leading-tight tracking-[-0.03em] text-ink">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-mute">{subtitle}</p>}
      </div>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-card border border-dashed border-line px-6 py-14 text-center">
      <p className="text-[15px] font-medium text-ink">{title}</p>
      {children && <p className="mt-1.5 max-w-sm text-sm text-mute">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="mb-4 rounded-ctl border border-crit/25 bg-crit/10 px-3.5 py-2.5 text-sm text-crit">
      {error}
    </p>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 aria-hidden className={cx("size-4 animate-spin text-mute", className)} />;
}

export function Loading() {
  return (
    <div className="flex h-48 items-center justify-center">
      <Spinner />
    </div>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cx("wordmark inline-flex items-center gap-2.5 text-[13px] text-ink", className)}>
      <svg viewBox="0 0 16 16" className="size-4" aria-hidden>
        <rect x="1.5" y="2" width="8.5" height="11" rx="0.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <path d="M6 5.5h8.5V15H6z" fill="currentColor" />
        <path d="M8 9h4.5" stroke="#4fb8a6" strokeWidth="1.6" />
      </svg>
      Tracefold
    </span>
  );
}

/** Imagery slot. With `src` it shows that image, cropped to fill (`position` picks the crop); without it, a placeholder
 * that says what belongs here. Preview images live in public/preview/, which git ignores. */
export function ImageSlot({
  label,
  className,
  children,
  src,
  position = "center",
  dim,
}: {
  label: string;
  className?: string;
  children?: ReactNode;
  src?: string;
  position?: string;
  /** 0–1: a grey wash over the image, to mute busy art behind text. */
  dim?: number;
}) {
  return (
    <div
      className={cx("image-slot overflow-hidden", !className?.includes("absolute") && "relative", className)}
      role="img"
      aria-label={src ? label : `Placeholder: ${label}`}
      style={src ? ({ "--slot-img": `url(${src})`, "--slot-pos": position, ...(dim ? { "--slot-dim": dim } : {}) } as React.CSSProperties) : undefined}
    >
      {!src && (
        <span className="absolute bottom-3 right-3 z-10 inline-flex items-center gap-1.5 rounded-md bg-black/45 px-2 py-1 text-[11px] text-white/80 backdrop-blur">
          <ImageIcon className="size-3" aria-hidden />
          {label}
        </span>
      )}
      {children}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] text-mute">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-faint">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "h-10 w-full rounded-ctl border border-[rgb(255_255_255/0.14)] bg-panel-2 px-3 text-sm text-ink outline-none transition-colors focus:border-accent/70";

