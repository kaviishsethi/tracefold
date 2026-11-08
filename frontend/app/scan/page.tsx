"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ChevronRight, FileText, Folder, FolderOpen, Upload, X } from "lucide-react";
import { listScans, startScan, uploadFiles, type ApiError, type Check, type Scan } from "@/lib/api";
import { bytes } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { Card, H1 } from "@/components/bits";
import { AgentPrompt } from "@/components/agent-prompt";
import { Checkbox } from "@/components/checkbox";
import { ScansTable } from "@/components/scans-table";
import { Button, ErrorNote, cx } from "@/components/ui";

const AGENT_SCAN =
  "Call the tracefold tool scan_changes for this repository (changes since HEAD, including untracked files). When it finishes, call get_findings with its scan_id, fix each local risk and call recheck_fix for it, and summarize the outcome. Don't print or test any secret value you see.";

/** Ready-made documents from docs/sample-documents, served from public/examples, one per company. Each was checked end to end with automatic search. */
const EXAMPLES = [
  {
    company: "Apple",
    file: "apple-internal-memo.md",
    doc: "Staff memo on leaks",
    kind: "Internal memo",
    shows: "Includes two sentences from Apple's 2021 staff memo that the press quoted word for word. Search finds that coverage.",
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
  const [samplesOpen, setSamplesOpen] = useState(false);
  async function loadExample(ex: (typeof EXAMPLES)[number]) {
    setLoadingExample(ex.file);
    setError(null);
    try {
      const res = await fetch(`/examples/${ex.file}`);
      if (!res.ok) throw new Error(`Couldn't load the ${ex.company} example.`);
      setFiles([new File([await res.blob()], ex.file, { type: "text/markdown" })]);
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
      const inp = await uploadFiles(workspace.id, files);
      const accepted = inp.files.filter((f) => f.status === "captured");
      if (!accepted.length) throw new Error(inp.files.map((f) => `${f.path}: ${f.reason}`).join("; ") || "No files could be read.");
      const checks: Check[] = publicToo ? ["public_match", "local_risk"] : ["local_risk"];
      const acc = await startScan(
        workspace.id,
        { input_id: inp.input_id, checks, ...(checks.includes("public_match") ? { automatic_discovery: true } : {}) },
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
        sub="Check files for leaked secrets, risky code and public copies."
        right={
          <>
            <AgentPrompt text={AGENT_SCAN} />
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
          <>
            <button onClick={() => input.current?.click()} className="flex w-full items-center gap-3 px-5 py-6 text-left text-sm text-mute hover:bg-panel-2">
              <FileText className="size-5 text-faint" aria-hidden />
              <span>
                Drag files anywhere on this page, or <span className="text-ink underline underline-offset-4">choose files</span>. Documents, code and .docx.
              </span>
            </button>
            <button
              onClick={() => setSamplesOpen((o) => !o)}
              aria-expanded={samplesOpen}
              className="flex w-full items-center gap-3 border-t border-line px-5 py-3 text-left text-sm text-ink-2 hover:bg-panel-2"
            >
              {samplesOpen ? <FolderOpen className="size-5 text-faint" aria-hidden /> : <Folder className="size-5 text-faint" aria-hidden />}
              <span className="flex-1">Sample files</span>
              <span className="text-xs text-faint">{EXAMPLES.length} files</span>
              <ChevronRight className={cx("size-4 text-faint transition-transform", samplesOpen && "rotate-90")} aria-hidden />
            </button>
            {samplesOpen && (
              <div className="border-t border-line bg-bg/40">
                {EXAMPLES.map((ex) => (
                  <div key={ex.file} className="flex items-center gap-3 py-2.5 pl-12 pr-5 text-sm">
                    <FileText className="size-4 shrink-0 text-faint" aria-hidden />
                    <button onClick={() => loadExample(ex)} disabled={loadingExample !== null} title={ex.shows} className="min-w-0 flex-1 truncate text-left text-ink hover:underline disabled:cursor-wait">
                      {loadingExample === ex.file ? "Loading…" : ex.file}
                    </button>
                    <span className="hidden truncate text-xs text-faint sm:block">
                      {ex.company} · {ex.doc}
                    </span>
                    <a href={`/examples/${ex.file}`} target="_blank" rel="noreferrer" className="shrink-0 text-xs text-mute hover:text-ink">
                      Open
                    </a>
                  </div>
                ))}
                <p className="py-2.5 pl-12 pr-5 text-xs text-faint">CivicActions and PostHog documents are public, used under their licenses. Neither endorses Tracefold.</p>
              </div>
            )}
          </>
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
              <div className="flex flex-wrap items-center justify-between gap-4">
                <Checkbox checked={publicToo} onChange={setPublicToo}>
                  Also check public pages
                </Checkbox>
                <Button onClick={run} loading={busy} className="!bg-accent !text-[#0a0c0c]">
                  Check {files.length} {files.length === 1 ? "file" : "files"}
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>

      <Card title="Recent scans" className="mt-6">
        <ScansTable scans={scans} empty="No scans yet. Scans from your coding assistant show up here too." />
      </Card>
    </div>
  );
}
