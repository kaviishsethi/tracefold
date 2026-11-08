"use client";

import { useState } from "react";
import { api, ws, type ApiError } from "@/lib/api";
import { Select } from "./select";
import { Button } from "./ui";

type Every = "hour" | "day" | "week";

/** "Schedule" on a finished scan: re-run the same check every hour, day or week. */
export function ScheduleButton({ workspaceId, scanId, publicCheck }: { workspaceId: string; scanId: string; publicCheck: boolean }) {
  const [open, setOpen] = useState(false);
  const [every, setEvery] = useState<Every>("day");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (done) return <span className="mr-2 text-xs text-local">{done}</span>;
  if (!open)
    return (
      <button type="button" onClick={() => setOpen(true)} className="mr-2 text-xs text-mute hover:text-ink">
        Schedule
      </button>
    );
  return (
    <span className="mr-2 flex flex-wrap items-center gap-2 text-xs">
      <span className="text-ink-2">Run this every</span>
      <Select<Every>
        label="How often"
        value={every}
        onChange={setEvery}
        options={[
          { value: "hour", label: "hour" },
          { value: "day", label: "day" },
          { value: "week", label: "week" },
        ]}
      />
      <Button
        size="sm"
        loading={busy}
        className="!bg-accent !text-[#0a0c0c]"
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await api(ws(workspaceId, "/schedules"), { method: "POST", json: { scan_id: scanId, every, public: publicCheck } });
            setDone(`Runs every ${every}. Manage it in Settings.`);
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
      <span className="basis-full text-faint">{error ?? "Keeps a private copy of these files on this machine so they can be checked again."}</span>
    </span>
  );
}
