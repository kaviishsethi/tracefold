"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { FileText, Upload, X } from "lucide-react";
import { api, ws, type Page, type QueryPlan, listScans, startScan, uploadFiles, type ApiError, type Check, type Scan } from "@/lib/api";
import { bytes } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { Card, Disclosure, H1 } from "@/components/bits";
import { AgentPrompt } from "@/components/agent-prompt";
import { ScansTable } from "@/components/scans-table";
import { Button, ErrorNote, cx } from "@/components/ui";

const AGENT_SCAN =
  "Call the tracefold tool scan_changes for this repository (changes since HEAD, including untracked files). When it finishes, call get_findings with its scan_id, fix each local risk and call recheck_fix for it, and summarize the outcome. Don't print or test any secret value you see.";

/** Ready-made documents from docs/demo-pairs, served from public/examples, one per company. Each was checked end to end with automatic search. */
const EXAMPLES = [
  {
    company: "Apple",
    file: "apple-mock-internal-memo.md",
    doc: "Mock internal memo",
    kind: "Simulated leak",
    shows: "Invented memo around two sentences from Apple's real 2021 leaked memo. Search finds the press coverage that quoted them.",
  },
  {
    company: "CivicActions",
    file: "civicactions-security-policy.md",
    doc: "Security policy",
    kind: "Published company document",
    shows: "An unchanged company policy. Search finds the public guidebook page that carries the same text.",
  },
  {
    company: "PostHog",
    file: "posthog-security.md",
    doc: "Security handbook page",
    kind: "Published company document",
    shows: "An unchanged handbook page. Search finds the live handbook, and the scan shows every passage that appears there.",
  },
];

const ext = (name: string) => (name.includes(".") ? name.split(".").pop()!.toUpperCase() : "File");

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
  const [automatic, setAutomatic] = useState(true);
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
      if (chosen) { setPlanId(chosen.query_plan_id); setAutomatic(false); }

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

  // The whole page accepts dropped files, like a file manager.
  useEffect(() => {
    let depth = 0;
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth++;
      setDragging(true);
    };
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const over = (e: DragEvent) => hasFiles(e) && e.preventDefault();
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDragging(false);
      add(e.dataTransfer?.files ?? null);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, []);

  const add = (list: FileList | null) => {
    if (!list) return;
    setFiles((prev) => [...prev, ...Array.from(list).filter((f) => !prev.some((p) => p.name === f.name))]);
  };

  const [loadingExample, setLoadingExample] = useState<string | null>(null);
  async function loadExample(ex: (typeof EXAMPLES)[number]) {
    setLoadingExample(ex.file);
    setError(null);
    try {
      const res = await fetch(`/examples/${ex.file}`);
      if (!res.ok) throw new Error(`Couldn't load the ${ex.company} example.`);
      setFiles([new File([await res.blob()], ex.file, { type: "text/markdown" })]);
      setAutomatic(true);
      setPublicToo(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingExample(null);
    }
  }

  async function run() {
    if (!workspace || !files.length) return;
    setBusy(true);
    setError(null);
    try {
      const selectedPlan = automatic ? undefined : plan;
      if (publicToo && !automatic && !selectedPlan && !manifest) throw new Error("Choose saved searches or use automatic search.");
      const inp = await uploadFiles(workspace.id, files);
      const accepted = inp.files.filter((f) => f.status === "captured");
      if (!accepted.length) throw new Error(inp.files.map((f) => `${f.path}: ${f.reason}`).join("; ") || "No files could be read.");
      const checks: Check[] = publicToo ? ["public_match", "local_risk"] : ["local_risk"];
      const acc = await startScan(
        workspace.id,
        { input_id: inp.input_id, checks, ...(checks.includes("public_match") ? (automatic ? { automatic_discovery: true } : selectedPlan ? { public_discovery: { query_plan_id: selectedPlan.query_plan_id, mode: "live" as const } } : { public_sources: { manifest_id: manifest!, mode: "refresh" as const } }) : {}) },
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
      <H1
        sub="Add files to check them for leaked secrets, risky code and copies on public pages."
        right={
          <>
            <AgentPrompt text={AGENT_SCAN} label="Have your agent scan" />
            <Button size="sm" onClick={() => input.current?.click()} className="!bg-accent !text-[#0a0c0c]">
              <Upload className="size-3.5" aria-hidden /> Upload files
            </Button>
          </>
        }
      >
        Scan
      </H1>
      <input ref={input} type="file" multiple hidden onChange={(e) => add(e.target.files)} />
      <ErrorNote error={error} />

      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-bg/80 backdrop-blur-sm">
          <div className="rounded-card border-2 border-dashed border-accent px-16 py-12 text-center">
            <Upload className="mx-auto size-6 text-accent" aria-hidden />
            <p className="mt-3 text-lg text-ink">Drop to add files</p>
          </div>
        </div>
      )}

      <Card
        title={files.length ? `${files.length} ${files.length === 1 ? "file" : "files"} ready` : "Files"}
        right={
          files.length > 0 ? (
            <button onClick={() => setFiles([])} className="text-xs text-mute hover:text-ink">
              Clear
            </button>
          ) : undefined
        }
      >
        {files.length === 0 ? (
          <button onClick={() => input.current?.click()} className="flex w-full items-center gap-3 px-5 py-6 text-left text-sm text-mute hover:bg-panel-2">
            <FileText className="size-5 text-faint" aria-hidden />
            <span>
              Drag files anywhere on this page, or <span className="text-ink underline underline-offset-4">choose files</span>. Documents, code and .docx.
            </span>
          </button>
        ) : (
          <>
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-faint">
                <tr className="border-b border-line">
                  <th className="px-5 py-2.5 font-normal">Name</th>
                  <th className="px-5 py-2.5 font-normal">Type</th>
                  <th className="px-5 py-2.5 text-right font-normal">Size</th>
                  <th className="w-12" />
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.name} className="border-b border-line last:border-0">
                    <td className="px-5 py-2.5">
                      <span className="flex min-w-0 items-center gap-2.5 text-ink">
                        <FileText className="size-4 shrink-0 text-faint" aria-hidden />
                        <span className="truncate">{f.name}</span>
                      </span>
                    </td>
                    <td className="px-5 py-2.5 text-xs text-faint">{ext(f.name)}</td>
                    <td className="px-5 py-2.5 text-right text-faint">{bytes(f.size)}</td>
                    <td className="pr-3 text-right">
                      <button onClick={() => setFiles(files.filter((x) => x !== f))} className="rounded-md p-1 text-faint hover:bg-raised hover:text-ink" aria-label={`Remove ${f.name}`}>
                        <X className="size-3.5" aria-hidden />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="space-y-3 border-t border-line px-5 py-4">
              {publicToo && (
                <label className="block text-sm text-mute">
                  Public sources
                  <select
                    className="mt-1.5 block w-full rounded-ctl border border-line bg-panel-2 px-3 py-2.5 text-ink"
                    value={automatic ? "__auto" : planId}
                    onChange={(e) => {
                      if (e.target.value === "__auto") setAutomatic(true);
                      else {
                        setAutomatic(false);
                        setPlanId(e.target.value);
                      }
                    }}
                  >
                    <option value="__auto">Automatic: search for company names found in the files</option>
                    {manifest && <option value="">Registered source list</option>}
                    {plans.map((p) => (
                      <option key={p.query_plan_id} value={p.query_plan_id}>
                        {p.display_name}, {p.pack ?? "discovery"}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {automatic && publicToo && (
                <p className="text-xs text-faint">Company names are identified locally and used to search public pages. Uploaded passages stay inside the engine.</p>
              )}
              {!automatic && plan && publicToo && (
                <Disclosure label="Preview public searches">
                  <ul className="space-y-2">
                    {plan.searches.map((q) => (
                      <li key={q.query_id}>
                        {q.provider}: <span className="text-ink">{q.query}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3">Only these approved queries are sent to search providers. Search is not exhaustive.</p>
                </Disclosure>
              )}
              <div className="flex flex-wrap items-center justify-between gap-4">
                <label className="flex items-center gap-2 text-sm text-ink-2">
                  <input type="checkbox" checked={publicToo} onChange={(e) => setPublicToo(e.target.checked)} />
                  Also look for copies on public pages
                </label>
                <Button onClick={run} loading={busy} className="!bg-accent !text-[#0a0c0c]">
                  Check {files.length} {files.length === 1 ? "file" : "files"}
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>

      <section className="mt-6" aria-labelledby="examples-title">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="examples-title" className="text-sm font-medium text-ink">
            Try an example
          </h2>
          <p className="text-xs text-faint">Loads a sample document, then press Check. Automatic search finds the company name in the text and looks for public copies.</p>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {EXAMPLES.map((ex) => {
            const selected = files.length === 1 && files[0].name === ex.file;
            return (
              <div
                key={ex.file}
                className={cx(
                  "flex flex-col rounded-card border bg-panel transition-colors",
                  selected ? "border-accent/60" : "border-line hover:border-line-strong",
                )}
              >
                <button
                  onClick={() => loadExample(ex)}
                  disabled={loadingExample !== null}
                  aria-pressed={selected}
                  className="flex flex-1 flex-col items-start gap-1 px-4 pb-3 pt-4 text-left disabled:cursor-wait"
                >
                  <span className="text-[11px] uppercase tracking-wide text-faint">{ex.kind}</span>
                  <span className="text-[15px] text-ink">{ex.company}</span>
                  <span className="text-[13px] text-ink-2">{ex.doc}</span>
                  <span className="mt-1 text-xs leading-relaxed text-mute">{ex.shows}</span>
                </button>
                <div className="flex items-center justify-between gap-3 whitespace-nowrap border-t border-line px-4 py-2.5 text-xs">
                  <a href={`/examples/${ex.file}`} target="_blank" rel="noreferrer" className="text-mute underline-offset-4 hover:text-ink hover:underline">
                    Read it
                  </a>
                  <button
                    onClick={() => loadExample(ex)}
                    disabled={loadingExample !== null}
                    className={cx("font-medium", selected ? "text-accent" : "text-ink-2 hover:text-ink")}
                  >
                    {loadingExample === ex.file ? "Loading…" : selected ? "Loaded ✓" : "Use example"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        <p className="mt-2 text-xs text-faint">
          The CivicActions and PostHog documents are unchanged public company documents, used under their licenses; neither company endorses Tracefold. The Apple memo is a simulation, not an Apple document.
        </p>
      </section>

      <Card title="Recent scans" className="mt-6" right={<span className="text-xs text-faint">From this app and your coding assistant</span>}>
        <ScansTable scans={scans} empty="No scans yet. Scans from your coding assistant show up here too." />
      </Card>
    </div>
  );
}
