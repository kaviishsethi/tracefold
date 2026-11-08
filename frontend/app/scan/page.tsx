"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, ws, type Page, type QueryPlan, listScans, startScan, uploadFiles, type ApiError, type Check, type Scan } from "@/lib/api";
import { bytes, relativeTime } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { Box, H1, Note, scanState, source } from "@/components/bits";
import { Button, ErrorNote, cx } from "@/components/ui";

export default function ScanPage() {
  const { current: workspace } = useCurrentWorkspace();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [publicToo, setPublicToo] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scans, setScans] = useState<Scan[] | null>(null);

  const manifest = workspace?.manifests[0];
  const [plans, setPlans] = useState<QueryPlan[]>([]);
  const [planId, setPlanId] = useState("");
  useEffect(() => {
    if (!workspace) return;
    let alive = true;
    setPlans([]);
    setPlanId("");
    api<Page<QueryPlan>>(ws(workspace.id, "/query-plans?limit=100")).then((p) => {
      if (!alive) return;
      setPlans(p.items);
      const requested = new URLSearchParams(window.location.search).get("plan");
      const chosen = p.items.find((x) => x.query_plan_id === requested);
      if (chosen) setPlanId(chosen.query_plan_id);
      else if (!workspace.manifests.length && p.items[0]) setPlanId(p.items[0].query_plan_id);
    }).catch(() => {});
    return () => { alive = false; };
  }, [workspace]);
  const plan = plans.find((p) => p.query_plan_id === planId);

  // Every scan from every client, refreshed so coding-assistant scans show up as they happen.
  useEffect(() => {
    if (!workspace) return;
    let alive = true;
    const load = () => listScans(workspace.id).then((p) => alive && setScans(p.items)).catch(() => alive && setScans([]));
    load();
    const t = setInterval(load, 4000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [workspace]);

  const add = (list: FileList | null) => {
    if (!list) return;
    setFiles((prev) => [...prev, ...Array.from(list).filter((f) => !prev.some((p) => p.name === f.name))]);
  };

  async function run() {
    if (!workspace || !files.length) return;
    setBusy(true);
    setError(null);
    try {
      const inp = await uploadFiles(workspace.id, files);
      const accepted = inp.files.filter((f) => f.status === "captured");
      if (!accepted.length) throw new Error(inp.files.map((f) => `${f.path}: ${f.reason}`).join("; ") || "No files could be read.");
      const checks: Check[] = (manifest || plan) && publicToo ? ["public_match", "local_risk"] : ["local_risk"];
      const acc = await startScan(
        workspace.id,
        { input_id: inp.input_id, checks, ...(checks.includes("public_match") ? (plan ? { public_discovery: { query_plan_id: plan.query_plan_id, mode: "live" as const } } : { public_sources: { manifest_id: manifest!, mode: "refresh" as const } }) : {}) },
        files.map((f) => f.name).join(", "),
      );
      router.push(`/scan/${acc.scan_id}`);
    } catch (e) {
      setError((e as ApiError).message);
      setBusy(false);
    }
  }

  return (
    <div>
      <H1 sub="Check files for leaked secrets and risky code, and for copies on public pages.">Scan</H1>
      <ErrorNote error={error} />

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          add(e.dataTransfer.files);
        }}
        onClick={() => input.current?.click()}
        className={cx(
          "flex cursor-pointer flex-col items-center justify-center rounded-card border border-dashed px-6 py-14 text-center transition-colors",
          dragging ? "border-accent bg-accent/5" : "border-line-strong hover:border-mute",
        )}
      >
        <p className="text-[17px] text-ink">Drop files to check</p>
        <p className="mt-1 text-sm text-mute">or click to choose. Documents, code and .docx.</p>
        <input ref={input} type="file" multiple hidden onChange={(e) => add(e.target.files)} />
      </div>

      {files.length > 0 && (
        <div className="mt-4">
          <Box>
            {files.map((f) => (
              <div key={f.name} className="flex items-center gap-3 border-t border-line px-4 py-2.5 text-sm first:border-t-0">
                <span className="min-w-0 flex-1 truncate text-ink">{f.name}</span>
                <span className="text-faint">{bytes(f.size)}</span>
                <button onClick={() => setFiles(files.filter((x) => x !== f))} className="text-mute hover:text-ink" aria-label={`Remove ${f.name}`}>
                  Remove
                </button>
              </div>
            ))}
          </Box>
          {plans.length > 0 && <label className="my-4 block text-sm text-mute">Public sources
            <select className="mt-2 block w-full rounded-ctl border border-line bg-panel px-3 py-3 text-ink" value={planId} onChange={(e) => setPlanId(e.target.value)}>
              {manifest && <option value="">Registered source list</option>}
              {plans.map((p) => <option key={p.query_plan_id} value={p.query_plan_id}>{p.display_name} — {p.pack ?? "discovery"}</option>)}
            </select>
          </label>}
          {plan && publicToo && <details className="my-4 text-sm text-mute"><summary className="cursor-pointer">Preview public searches</summary><ul className="mt-3 space-y-2">{plan.searches.map((q) => <li key={q.query_id}>{q.provider}: <span className="text-ink">{q.query}</span></li>)}</ul><p className="mt-3">Only these approved queries are sent to search providers. Search is not exhaustive.</p></details>}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
            {manifest || plans.length ? (
              <label className="flex items-center gap-2 text-sm text-ink-2">
                <input type="checkbox" checked={publicToo} onChange={(e) => setPublicToo(e.target.checked)} />
                Also look for copies on public pages
              </label>
            ) : (
              <span className="text-sm text-faint">No public pages registered, so only your files are checked.</span>
            )}
            <Button onClick={run} loading={busy}>
              Check {files.length} {files.length === 1 ? "file" : "files"}
            </Button>
          </div>
        </div>
      )}

      <h2 className="mb-3 mt-14 text-sm font-medium text-ink">Recent scans</h2>
      <Box>
        {scans === null ? (
          <Note>Loading…</Note>
        ) : scans.length === 0 ? (
          <Note>No scans yet. Scans from your coding assistant show up here too.</Note>
        ) : (
          scans.map((s) => {
            const st = scanState(s);
            const n = typeof s.summary.observations === "number" ? s.summary.observations : null;
            return (
              <Link key={s.scan_id} href={`/scan/${s.scan_id}`} className="flex items-center gap-3 border-t border-line px-4 py-3 text-sm first:border-t-0 hover:bg-panel-2">
                <span className={cx("size-2 rounded-full", st.tone === "busy" ? "animate-pulse bg-accent" : st.tone === "done" ? "bg-local" : "bg-med")} />
                <span className="w-36 shrink-0 text-ink">{source(s)}</span>
                <span className="min-w-0 flex-1 truncate text-mute">
                  {s.recheck_of ? "Recheck · " : ""}
                  {st.tone === "busy" ? st.text : n === null ? st.text : n === 0 ? "Nothing found" : `${n} found`}
                </span>
                <span className="shrink-0 text-faint">{relativeTime(s.created_at)}</span>
              </Link>
            );
          })
        )}
      </Box>
    </div>
  );
}
