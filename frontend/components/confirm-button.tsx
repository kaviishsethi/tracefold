"use client";

import { useState, type ReactNode } from "react";
import { cx } from "./ui";

/** A quiet text button that asks once ("Delete 5 scans?  Delete · Cancel") before running. */
export function ConfirmButton({
  label,
  question,
  confirm = "Delete",
  onConfirm,
  className,
}: {
  label: ReactNode;
  question: string;
  confirm?: string;
  onConfirm: () => Promise<unknown> | void;
  className?: string;
}) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!asking)
    return (
      <button type="button" onClick={() => setAsking(true)} className={cx("text-xs text-mute hover:text-ink", className)}>
        {label}
      </button>
    );
  return (
    <span className="flex items-center gap-3 text-xs">
      <span className="text-ink-2">{question}</span>
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onConfirm();
          } finally {
            setBusy(false);
            setAsking(false);
          }
        }}
        className="font-medium text-crit hover:underline disabled:opacity-50"
      >
        {busy ? "Deleting…" : confirm}
      </button>
      <button type="button" onClick={() => setAsking(false)} className="text-mute hover:text-ink">
        Cancel
      </button>
    </span>
  );
}
