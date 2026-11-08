"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { ArrowRight, Check, ChevronRight, FileText, FolderGit2, Upload, X } from "lucide-react";
import {
  api,
  recentScans,
  startScan,
  uploadFiles,
  ws,
  type ApiError,
  type Capabilities,
  type Check as CheckId,
  type Input,
  type Page,
  type QueryPlan,
  type RecentScan,
} from "@/lib/api";
import { searchFilters } from "@/components/discovery";
import { bytes, relativeTime, shortId } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { Select } from "@/components/select";
import { Button, Empty, ErrorNote, Loading, PageHeader, Panel, Spinner, cx, inputClass } from "@/components/ui";

const STEPS = [
  ["Capture", "Your files are read into the engine's memory. Nothing is written to disk, and a capture expires on its own."],
  ["Parse", "Text, code and .docx files are split into passages with stable line or paragraph locations."],
  ["Find and fetch public pages", "Only for public exposure: a separate worker fetches the URLs in a source list, or searches with an approved discovery plan and fetches the results. It never sees your files."],
  ["Compare", "Your passages are matched against the fetched public text."],
  ["Local rules", "Deterministic rules look for secrets, personal data and risky code in your files."],
  ["Model review", "Optional. A local model reviews rule hits and explains them. It only runs on loopback."],
  ["Publish", "Findings are stored with their evidence. Takedown and key-disable actions are drafted for a person to approve."],
];

const ACCEPT =
  ".txt,.md,.markdown,.rst,.csv,.json,.yaml,.yml,.toml,.ini,.cfg,.env,.py,.js,.jsx,.ts,.tsx,.go,.rs,.java,.kt,.rb,.php,.c,.h,.cpp,.cs,.swift,.sh,.sql,.tf,.docx";

function Toggle({
  checked,
  onChange,
  title,
  hint,
  disabled,
  children,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  title: string;
  hint?: ReactNode;
  disabled?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className={cx("border-b border-line px-4 py-3.5 last:border-0", disabled && "opacity-60")}>
      <label className={cx("flex items-start gap-3", disabled ? "cursor-not-allowed" : "cursor-pointer")}>
        <input type="checkbox" className="peer sr-only" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
        <span
          aria-hidden
          className={cx(
            "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-[5px] border transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-accent/60",
            checked ? "border-ink bg-ink text-[#0a0a0a]" : "border-line-strong bg-panel-2",
          )}
        >
          {checked && <Check className="size-3" strokeWidth={3} />}
        </span>
        <span className="min-w-0">
          <span className="block text-[13px] font-medium text-ink">{title}</span>
          {hint && <span className="mt-0.5 block text-xs leading-relaxed text-mute">{hint}</span>}
        </span>
      </label>
      {children && <div className="ml-7 mt-3">{children}</div>}
    </div>
  );
}

function CapturedList({ input, onClear }: { input: Input; onClear: () => void }) {
  const ok = input.files.filter((f) => f.status !== "rejected");
  const bad = input.files.filter((f) => f.status === "rejected");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(t);
  }, []);
  const mins = Math.round((+new Date(input.expires_at) - now) / 60000);
  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-2.5 text-xs">
        <span className="text-ink-2">
          {ok.length} accepted{bad.length ? `, ${bad.length} rejected` : ""}
        </span>
        <span className="font-mono text-faint">{shortId(input.input_id)}</span>
        {input.baseline && <span className="text-faint">since {input.baseline}</span>}
        <span className={cx("ml-auto", mins <= 2 ? "text-med" : "text-faint")}>{mins > 0 ? `Expires in ${mins} min` : "Expired. Capture again."}</span>
        <button onClick={onClear} className="inline-flex items-center gap-1 text-mute hover:text-ink">
          <X className="size-3" aria-hidden /> Clear
        </button>
      </div>
      {input.files.length === 0 ? (
        <p className="px-4 py-6 text-[13px] text-mute">Nothing to capture. There are no changes since the baseline.</p>
      ) : (
        <ul className="scroll-thin max-h-64 divide-y divide-line overflow-auto">
          {input.files.map((f) => (
            <li key={f.file_id} className="flex items-center gap-3 px-4 py-2 text-[13px]">
              {f.status === "rejected" ? (
                <X className="size-3.5 shrink-0 text-crit" aria-label="rejected" />
              ) : (
                <Check className="size-3.5 shrink-0 text-local" aria-label={f.status} />
              )}
              <span className={cx("min-w-0 flex-1 truncate font-mono text-xs", f.status === "rejected" ? "text-mute" : "text-ink")}>{f.path ?? f.file_id}</span>
              {f.change && <span className="text-xs text-faint">{f.change}</span>}
              {f.status === "deleted" && <span className="text-xs text-faint">deleted</span>}
              {f.status === "rejected" ? (
                <span className="shrink-0 text-xs text-crit">{f.reason ?? "rejected"}</span>
              ) : (
                <span className="shrink-0 font-mono text-xs text-faint">
                  {f.kind ?? ""} {f.size != null ? bytes(f.size) : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {input.omitted_context.length > 0 && <p className="border-t border-line px-4 py-2.5 text-xs text-faint">Not included: {input.omitted_context.join(", ")}</p>}
    </div>
  );
}

export default function NewScan() {
  const router = useRouter();
  const { current } = useCurrentWorkspace();
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [capsError, setCapsError] = useState<string | null>(null);
  const [source, setSource] = useState<"upload" | "workspace">("upload");
  const [input, setInput] = useState<Input | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [mode, setMode] = useState<"changes" | "files">("changes");
  const [paths, setPaths] = useState("");
  const [localRisk, setLocalRisk] = useState(true);
  const [publicMatch, setPublicMatch] = useState(false);
  const [manifest, setManifest] = useState("");
  const [plans, setPlans] = useState<QueryPlan[]>([]);
  const [publicKind, setPublicKind] = useState<"list" | "discovery">("list");
  const [planId, setPlanId] = useState("");
  const [modelReview, setModelReview] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<RecentScan[]>([]);
  const picker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<Capabilities>("/capabilities")
      .then(setCaps)
      .catch((e: ApiError) => setCapsError(e.message));
  }, []);

  useEffect(() => {
    if (!current) return;
    let alive = true;
    api<Page<QueryPlan>>(ws(current.id, "/query-plans?limit=100"))
      .then(({ items }) => {
        if (!alive) return;
        const sorted = [...items].sort((a, b) => b.created_at.localeCompare(a.created_at));
        setPlans(sorted);
        const wanted = new URLSearchParams(window.location.search).get("plan");
        const pick = sorted.find((p) => p.query_plan_id === wanted) ?? sorted[0];
        setPlanId(pick?.query_plan_id ?? "");
        if (wanted && pick?.query_plan_id === wanted) {
          setPublicMatch(true);
          setPublicKind("discovery");
        } else if (!current.manifests.length && sorted.length) setPublicKind("discovery");
      })
      .catch(() => alive && setPlans([]));
    return () => {
      alive = false;
    };
  }, [current]);

  useEffect(() => {
    setRecent(current ? recentScans(current.id) : []);
    setManifest(current?.manifests[0] ?? "");
    setInput(null);
    setSkipped([]);
    setSource(current?.source_type === "local_dir" ? "workspace" : "upload");
  }, [current]);

  if (capsError) return <ErrorNote error={capsError} />;
  if (!caps) return <Loading />;
  if (!current)
    return (
      <Empty
        title="No workspace"
        action={
          <Link href="/onboarding" className="text-sm text-ink underline-offset-4 hover:underline">
            Setup steps
          </Link>
        }
      >
        This app&apos;s token doesn&apos;t cover a workspace yet.
      </Empty>
    );

  const maxFiles = caps.limits.max_files_per_capture ?? 10;
  const maxBytes = caps.limits.max_file_bytes ?? 5 * 1024 * 1024;
  const canSubmit = current.capabilities.includes("submit");
  const localDir = current.source_type === "local_dir";
  const modelUp = caps.model.available === true;
  const accepted = input?.files.filter((f) => f.status === "captured").length ?? 0;
  const checks: CheckId[] = [];
  if (localRisk) checks.push("local_risk");
  if (publicMatch) checks.push("public_match");
  const plan = plans.find((p) => p.query_plan_id === planId) ?? null;
  const publicReady = publicKind === "list" ? !!manifest : !!plan;
  const ready = !!input && accepted > 0 && checks.length > 0 && (!publicMatch || publicReady) && canSubmit;

  async function upload(list: File[]) {
    if (!current) return;
    const tooBig = list.filter((f) => f.size > maxBytes);
    const fits = list.filter((f) => f.size <= maxBytes);
    const keep = fits.slice(0, maxFiles);
    setSkipped([
      ...tooBig.map((f) => `${f.name}: larger than ${bytes(maxBytes)}`),
      ...fits.slice(maxFiles).map((f) => `${f.name}: over the ${maxFiles}-file limit per capture`),
    ]);
    if (!keep.length) return;
    setCapturing(true);
    setError(null);
    try {
      setInput(await uploadFiles(current.id, keep));
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setCapturing(false);
    }
  }

  async function capture() {
    if (!current) return;
    setCapturing(true);
    setError(null);
    setSkipped([]);
    try {
      const body =
        mode === "changes"
          ? { mode: "changes", baseline: "HEAD", include_untracked: true }
          : {
              mode: "files",
              paths: paths
                .split("\n")
                .map((p) => p.trim())
                .filter(Boolean),
            };
      setInput(await api<Input>(ws(current.id, "/captures"), { method: "POST", json: body }));
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setCapturing(false);
    }
  }

  async function submit() {
    if (!current || !input) return;
    setSubmitting(true);
    setError(null);
    const names = input.files.filter((f) => f.status === "captured").map((f) => f.path ?? f.file_id);
    const label =
      source === "upload"
        ? `Upload: ${names.slice(0, 3).join(", ")}${names.length > 3 ? ` +${names.length - 3}` : ""}`
        : mode === "changes"
          ? `Changes since HEAD (${accepted} ${accepted === 1 ? "file" : "files"})`
          : `Workspace files: ${names.slice(0, 3).join(", ")}${names.length > 3 ? ` +${names.length - 3}` : ""}`;
    try {
      const acc = await startScan(
        current.id,
        {
          input_id: input.input_id,
          checks,
          ...(publicMatch
            ? publicKind === "list"
              ? { public_sources: { manifest_id: manifest, mode: "refresh" as const } }
              : { public_discovery: { query_plan_id: planId, mode: "live" as const } }
            : {}),
          model_review: localRisk && modelReview,
        },
        label,
      );
      router.push(`/scan/${acc.scan_id}`);
    } catch (e) {
      setError((e as ApiError).message);
      setSubmitting(false);
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (!capturing && canSubmit) upload(Array.from(e.dataTransfer.files));
  }

  return (
    <div>
      <PageHeader title="New scan" subtitle="Check files for potential risks, and for passages that already appear on approved public pages." />

      {!canSubmit && (
        <p className="mb-4 rounded-ctl border border-med/25 bg-med/10 px-3.5 py-2.5 text-sm text-med">
          This app&apos;s grant for {current.name} doesn&apos;t include <code className="font-mono">submit</code>, so it can&apos;t start scans.
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-6">
          <Panel
            title="Files"
            meta={`up to ${maxFiles} files, ${bytes(maxBytes)} each`}
            actions={
              localDir ? (
                <div role="tablist" aria-label="Source" className="flex gap-1">
                  {(
                    [
                      ["workspace", "Workspace folder"],
                      ["upload", "Upload"],
                    ] as const
                  ).map(([v, l]) => (
                    <button
                      key={v}
                      role="tab"
                      aria-selected={source === v}
                      onClick={() => {
                        setSource(v);
                        setInput(null);
                        setSkipped([]);
                      }}
                      className={cx("h-7 rounded-md px-2.5 text-xs font-medium transition-colors", source === v ? "bg-raised text-ink" : "text-mute hover:text-ink")}
                    >
                      {l}
                    </button>
                  ))}
                </div>
              ) : undefined
            }
          >
            {input ? (
              <CapturedList
                input={input}
                onClear={() => {
                  setInput(null);
                  setSkipped([]);
                }}
              />
            ) : source === "upload" ? (
              <div className="p-4">
                <button
                  type="button"
                  onClick={() => picker.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={onDrop}
                  disabled={capturing || !canSubmit}
                  className={cx(
                    "flex min-h-[188px] w-full flex-col items-center justify-center rounded-card border border-dashed px-6 py-10 text-center transition-colors duration-150",
                    dragging ? "border-accent/70 bg-accent/[0.06]" : "border-line-strong hover:border-[#5a5a55] hover:bg-panel-2",
                  )}
                >
                  {capturing ? (
                    <span className="flex items-center gap-2 text-[13px] text-mute">
                      <Spinner /> Uploading to the engine
                    </span>
                  ) : (
                    <>
                      <span className="flex size-10 items-center justify-center rounded-ctl border border-line bg-panel-2">
                        <Upload className="size-4 text-mute" aria-hidden />
                      </span>
                      <span className="mt-4 text-sm font-medium text-ink">Drop files here, or choose files</span>
                      <span className="mt-1 text-xs text-faint">Text, Markdown, source code and .docx</span>
                    </>
                  )}
                </button>
                <input
                  ref={picker}
                  type="file"
                  multiple
                  accept={ACCEPT}
                  className="hidden"
                  onChange={(e) => {
                    upload(Array.from(e.target.files ?? []));
                    e.target.value = "";
                  }}
                />
                <p className="mt-3 text-xs text-faint">
                  The engine holds uploads in memory for {Math.round((caps.limits.capture_ttl_seconds ?? 900) / 60)} minutes, then drops them.
                </p>
              </div>
            ) : (
              <div className="space-y-4 p-4">
                <div className="grid gap-2 sm:grid-cols-2">
                  {(
                    [
                      ["changes", "Changes since HEAD", "Modified, added and untracked files in the registered Git folder."],
                      ["files", "Specific files", "Paths relative to the workspace folder, one per line."],
                    ] as const
                  ).map(([v, t, d]) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setMode(v)}
                      aria-pressed={mode === v}
                      className={cx("rounded-ctl border p-3 text-left transition-colors", mode === v ? "border-line-strong bg-raised" : "border-line hover:bg-panel-2")}
                    >
                      <span className="flex items-center gap-2 text-[13px] font-medium text-ink">
                        {v === "changes" ? <FolderGit2 className="size-3.5 text-mute" aria-hidden /> : <FileText className="size-3.5 text-mute" aria-hidden />}
                        {t}
                      </span>
                      <span className="mt-1 block text-xs text-mute">{d}</span>
                    </button>
                  ))}
                </div>
                {mode === "files" && (
                  <textarea
                    value={paths}
                    onChange={(e) => setPaths(e.target.value)}
                    rows={4}
                    aria-label="File paths"
                    placeholder={"docs/roadmap.md\nsrc/config.py"}
                    className={cx(inputClass, "h-auto py-2 font-mono text-[13px]")}
                  />
                )}
                <Button variant="secondary" onClick={capture} loading={capturing} disabled={!canSubmit || (mode === "files" && !paths.trim())}>
                  Capture files
                </Button>
              </div>
            )}
            {skipped.length > 0 && (
              <ul className="border-t border-line px-4 py-2.5 text-xs text-med">
                {skipped.map((s) => (
                  <li key={s}>Not uploaded: {s}</li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Checks">
            <Toggle
              checked={localRisk}
              onChange={setLocalRisk}
              title="Potential risks in your files"
              hint={`Secrets, personal data and risky code, found by ${caps.local_risk_rules.length} local rules.`}
            >
              {localRisk && (
                <label className="flex cursor-pointer flex-wrap items-center gap-2 text-xs text-mute">
                  <input type="checkbox" checked={modelReview} onChange={(e) => setModelReview(e.target.checked)} className="accent-[#fafafa]" />
                  Ask the local model to review rule hits
                  {!modelUp && <span className="text-med">· The model is unavailable, so hits will say &ldquo;Model review unavailable&rdquo;.</span>}
                </label>
              )}
            </Toggle>
            <Toggle
              checked={publicMatch}
              onChange={setPublicMatch}
              disabled={current.manifests.length === 0 && plans.length === 0}
              title="Public exposure"
              hint={
                current.manifests.length === 0 && plans.length === 0 ? (
                  <>
                    This workspace has no approved source list or discovery plan yet.{" "}
                    <Link href="/discovery" className="text-ink-2 underline-offset-4 hover:underline">
                      Set up discovery
                    </Link>
                  </>
                ) : (
                  "Look for your passages on public pages: a fixed source list, or pages found by searching the company's public name."
                )
              }
            >
              {publicMatch && (
                <div className="space-y-3">
                  <div role="tablist" aria-label="Public pages" className="flex gap-1">
                    {(
                      [
                        ["list", "Source list", current.manifests.length > 0],
                        ["discovery", "Company discovery", plans.length > 0],
                      ] as const
                    ).map(([v, l, enabled]) => (
                      <button
                        key={v}
                        role="tab"
                        aria-selected={publicKind === v}
                        disabled={!enabled}
                        onClick={() => setPublicKind(v)}
                        className={cx(
                          "h-7 rounded-md px-2.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                          publicKind === v ? "bg-raised text-ink" : "text-mute hover:text-ink",
                        )}
                      >
                        {l}
                      </button>
                    ))}
                  </div>
                  {publicKind === "list" ? (
                    <div className="flex flex-wrap items-center gap-3">
                      <Select label="Source list" value={manifest} onChange={setManifest} options={current.manifests.map((m) => ({ value: m, label: m }))} />
                      <span className="text-xs text-faint">Fresh fetch, up to {caps.limits.max_public_pages ?? 20} pages</span>
                    </div>
                  ) : plan ? (
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-3">
                        <Select
                          label="Discovery plan"
                          value={planId}
                          onChange={setPlanId}
                          options={plans.map((p) => ({
                            value: p.query_plan_id,
                            label: `${p.display_name} · ${p.pack ?? [...new Set(p.searches.map((x) => x.template_id))].join(", ")}`,
                          }))}
                        />
                        <Link href="/discovery" className="text-xs text-mute hover:text-ink">
                          Manage plans
                        </Link>
                      </div>
                      <div className="rounded-ctl border border-line bg-panel-2/60">
                        <p className="border-b border-line px-3 py-2 text-xs text-faint">Sent to the search providers, nothing else:</p>
                        <ul className="divide-y divide-line">
                          {plan.searches.map((q) => (
                            <li key={q.query_id} className="flex flex-wrap items-baseline gap-x-2 px-3 py-1.5 text-xs">
                              <span className="w-12 shrink-0 font-mono text-faint">{q.provider}</span>
                              <span className="font-mono text-ink-2">{q.query}</span>
                              <span className="text-faint">{searchFilters(q)}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                      <p className="text-xs text-faint">
                        Up to {caps.limits.max_public_pages ?? 20} returned pages are fetched and compared on this machine. Search isn&apos;t exhaustive.
                      </p>
                    </div>
                  ) : (
                    <p className="text-xs text-mute">
                      No discovery plan yet.{" "}
                      <Link href="/discovery" className="text-ink-2 underline-offset-4 hover:underline">
                        Create one
                      </Link>
                    </p>
                  )}
                </div>
              )}
            </Toggle>
          </Panel>

          <ErrorNote error={error} />

          <div className="flex flex-wrap items-center justify-end gap-3">
            <p className="mr-auto text-xs text-faint">
              {!input
                ? "Add files to continue."
                : accepted === 0
                  ? "No file was accepted. See the reasons above."
                  : checks.length === 0
                    ? "Pick at least one check."
                    : `${accepted} ${accepted === 1 ? "file" : "files"} · ${checks.length === 2 ? "both checks" : publicMatch ? "public exposure" : "potential risks"}`}
            </p>
            <Button onClick={submit} loading={submitting} disabled={!ready}>
              Start scan <ArrowRight className="size-4" aria-hidden />
            </Button>
          </div>

          <Panel title="Recent scans" meta="remembered by this browser">
            {recent.length === 0 ? (
              <p className="px-4 py-6 text-[13px] text-mute">
                No scans started from this browser yet. The engine doesn&apos;t list past scans, so scans run from another device or a coding assistant won&apos;t show
                here.
              </p>
            ) : (
              <ul className="divide-y divide-line">
                {recent.slice(0, 10).map((s) => (
                  <li key={s.scan_id}>
                    <Link href={`/scan/${s.scan_id}`} className="group flex items-center gap-4 px-4 py-3 text-[13px] transition-colors hover:bg-panel-2">
                      <span className="font-mono text-ink">{shortId(s.scan_id)}</span>
                      <span className="min-w-0 flex-1 truncate text-ink-2">{s.label}</span>
                      <span className="shrink-0 text-faint">{relativeTime(s.at)}</span>
                      <ChevronRight className="size-4 text-faint transition-transform group-hover:translate-x-0.5" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <Panel title="How a scan works" className="self-start">
          <ol>
            {STEPS.map(([t, d], i) => (
              <li key={t} className="flex gap-3 border-b border-line px-4 py-3 last:border-0">
                <span className="w-5 pt-px font-mono text-xs text-accent">{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <p className="text-[13px] font-medium text-ink">{t}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-mute">{d}</p>
                </div>
              </li>
            ))}
          </ol>
        </Panel>
      </div>
    </div>
  );
}
