"use client";

import { useState } from "react";
import { api, ws, type ApiError } from "@/lib/api";
import { Select } from "./select";
import { Button, cx, inputClass } from "./ui";

type Unit = "seconds" | "minutes" | "hours" | "days" | "weeks";
const SECONDS: Record<Unit, number> = { seconds: 1, minutes: 60, hours: 3600, days: 86400, weeks: 604800 };

/** "Every 90 minutes", "every day", "every 2 weeks". */
export function describeInterval(seconds: number): string {
  for (const u of ["weeks", "days", "hours", "minutes"] as Unit[]) {
    if (seconds % SECONDS[u] === 0) {
      const n = seconds / SECONDS[u];
      return n === 1 ? `every ${u.slice(0, -1)}` : `every ${n} ${u}`;
    }
  }
  return `every ${seconds} seconds`;
}

/** Local "YYYY-MM-DDTHH:MM" for a date-time field, a few minutes from now. */
function soon(): string {
  const d = new Date(Date.now() + 5 * 60_000);
  d.setSeconds(0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "Schedule" on a finished scan: re-run the same check at an exact interval, starting when you choose. */
export function ScheduleButton({ workspaceId, scanId, publicCheck }: { workspaceId: string; scanId: string; publicCheck: boolean }) {
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState("1");
  const [unit, setUnit] = useState<Unit>("days");
  const [start, setStart] = useState(soon);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const n = Math.floor(Number(count));
  const seconds = n > 0 ? n * SECONDS[unit] : 0;
  const valid = seconds >= 10 && seconds <= 31_536_000 && !!start;

  if (done) return <span className="mr-2 text-xs text-local">{done}</span>;
  return (
    <span className="relative mr-2">
      <button type="button" onClick={() => setOpen((o) => !o)} className="text-xs text-mute hover:text-ink">
        Schedule
      </button>
      {open && (
    <div className="absolute right-0 top-full z-30 mt-2 w-[340px] space-y-3 rounded-card border border-line-strong bg-panel p-4 text-left text-xs shadow-[0_16px_40px_-8px_rgb(0_0_0/0.7)]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-ink-2">Run every</span>
        <input
          aria-label="How many"
          inputMode="numeric"
          value={count}
          onChange={(e) => setCount(e.target.value.replace(/[^0-9]/g, "").slice(0, 6))}
          className={cx(inputClass, "!h-8 !min-h-0 !w-16 !px-2 text-center text-[13px]")}
        />
        <Select<Unit>
          label="Unit"
          value={unit}
          onChange={setUnit}
          options={(["seconds", "minutes", "hours", "days", "weeks"] as Unit[]).map((u) => ({ value: u, label: u }))}
        />
      </div>
      <label className="flex flex-wrap items-center gap-2">
        <span className="text-ink-2">Starting</span>
        <input
          type="datetime-local"
          value={start}
          onChange={(e) => setStart(e.target.value)}
          className={cx(inputClass, "!h-8 !min-h-0 !w-auto flex-1 text-[13px] [color-scheme:dark]")}
        />
      </label>
      <p className={error ? "text-crit" : "text-faint"}>
        {error ??
          (seconds && seconds < 10
            ? "The shortest interval is 10 seconds."
            : "Keeps a private copy of these files on this machine so they can be checked again.")}
      </p>
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          loading={busy}
          disabled={!valid}
          className="!bg-accent !text-[#0a0c0c]"
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await api(ws(workspaceId, "/schedules"), {
                method: "POST",
                json: { scan_id: scanId, interval_seconds: seconds, start_at: new Date(start).toISOString(), public: publicCheck },
              });
              setDone(`Runs ${describeInterval(seconds)}. Manage it in Settings.`);
            } catch (e) {
              setError((e as ApiError).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Schedule
        </Button>
        <button type="button" onClick={() => setOpen(false)} className="text-mute hover:text-ink">
          Cancel
        </button>
      </div>
    </div>
      )}
    </span>
  );
}
