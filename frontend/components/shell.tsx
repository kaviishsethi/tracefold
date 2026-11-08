"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { CheckSquare, ChevronRight, ChevronsUpDown, Database, Globe, LayoutGrid, Radar, ScanSearch, Settings2, ShieldAlert, Upload } from "lucide-react";
import { api, useWorkspace, ws, type Action, type ApiError, type Capabilities, type Finding, type Page, type Workspace } from "@/lib/api";
import { LinkButton, Spinner, cx } from "./ui";

/** Marketing pages: no engine needed, no app chrome. */
export const PUBLIC_PATHS = ["/", "/manifesto", "/enterprise", "/pricing", "/security", "/contact"];

const NAV = [
  { href: "/overview", label: "Overview", icon: LayoutGrid },
  { href: "/findings", label: "Findings", icon: ShieldAlert },
  { href: "/actions", label: "Approvals", icon: CheckSquare },
  { href: "/scan", label: "Scans", icon: ScanSearch },
  { href: "/egress", label: "Egress", icon: Radar },
  { href: "/discovery", label: "Discovery", icon: Globe },
  { href: "/sources", label: "Sources", icon: Database },
  { href: "/settings", label: "Settings", icon: Settings2 },
];

// ---------- current workspace, shared with every app page ----------
interface WorkspaceState {
  list: Workspace[];
  current: Workspace | null;
  error: ApiError | null;
  ready: boolean;
  select: (id: string) => void;
}

const WorkspaceCtx = createContext<WorkspaceState>({ list: [], current: null, error: null, ready: false, select: () => {} });

/** The workspace the user is working in. `current` is null until loaded, or when the app has no grant. */
export function useCurrentWorkspace() {
  return useContext(WorkspaceCtx);
}

// ---------- breadcrumbs: pages can name the last crumb (e.g. a finding's title) ----------
const CrumbCtx = createContext<(label: string | null) => void>(() => {});

export function useCrumb(label: string | null | undefined) {
  const set = useContext(CrumbCtx);
  useEffect(() => {
    set(label ?? null);
    return () => set(null);
  }, [label, set]);
}

export function NewScanButton({ variant = "primary", size = "sm" }: { variant?: "primary" | "secondary"; size?: "sm" | "md" }) {
  return (
    <LinkButton href="/scan" variant={variant} size={size}>
      <Upload className="size-3.5" aria-hidden />
      New scan
    </LinkButton>
  );
}

function useCounts(workspaceId: string | null) {
  const [counts, setCounts] = useState<{ open: number | null; approvals: number | null }>({ open: null, approvals: null });
  const path = usePathname();
  useEffect(() => {
    if (!workspaceId) return;
    api<Page<Finding>>(ws(workspaceId, "/findings?limit=100"))
      .then((p) => setCounts((c) => ({ ...c, open: p.items.filter((f) => f.status === "open").length })))
      .catch(() => setCounts((c) => ({ ...c, open: null })));
    api<Page<Action>>(ws(workspaceId, "/actions?status=drafted&limit=100"))
      .then((p) => setCounts((c) => ({ ...c, approvals: p.items.length })))
      .catch(() => setCounts((c) => ({ ...c, approvals: null })));
  }, [path, workspaceId]);
  return counts;
}

function WorkspaceSwitcher({ state }: { state: WorkspaceState }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const cur = state.current;
  return (
    <div ref={root} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={cx("flex w-full items-center gap-2.5 rounded-ctl px-2 py-1.5 text-left transition-colors duration-150", open ? "bg-panel-2" : "hover:bg-panel")}
      >
        <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-ink text-[13px] font-semibold text-[#0a0a0a]">
          {(cur?.name ?? "T").charAt(0).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium text-ink">{cur?.name ?? "No workspace"}</span>
          <span className="block truncate text-[11px] text-faint">
            {cur ? `${cur.source_type === "local_dir" ? "Local folder" : "Uploads only"} · ${cur.disclosure} disclosure` : "Connect the engine"}
          </span>
        </span>
        <ChevronsUpDown className="size-3.5 shrink-0 text-faint" aria-hidden />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute left-0 right-0 top-[calc(100%+6px)] z-50 origin-top animate-[menu-in_140ms_cubic-bezier(.16,1,.3,1)] rounded-ctl border border-line-strong bg-[#1a1a1a] p-1 shadow-[0_16px_40px_-8px_rgb(0_0_0/0.7)]"
        >
          {state.list.map((w) => (
            <button
              key={w.id}
              role="menuitemradio"
              aria-checked={w.id === cur?.id}
              onClick={() => {
                state.select(w.id);
                setOpen(false);
              }}
              className={cx(
                "flex w-full items-center justify-between gap-2 rounded-[7px] px-2.5 py-1.5 text-left text-[13px] hover:bg-raised",
                w.id === cur?.id ? "text-ink" : "text-ink-2",
              )}
            >
              <span className="truncate">{w.name}</span>
              <span className="font-mono text-[11px] text-faint">{w.id}</span>
            </button>
          ))}
          <Link
            role="menuitem"
            href="/onboarding"
            onClick={() => setOpen(false)}
            className="mt-1 flex items-center gap-2 border-t border-line px-2.5 pb-1 pt-2 text-[13px] text-ink-2 hover:text-ink"
          >
            <Settings2 className="size-3.5" aria-hidden /> Set up a workspace
          </Link>
        </div>
      )}
    </div>
  );
}

/** Engine status in the sidebar foot: whether scans can run here, and whether the local model is up. */
function EngineStatus() {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  useEffect(() => {
    api<Capabilities>("/capabilities")
      .then(setCaps)
      .catch(setErr);
  }, []);
  const modelUp = caps?.model?.available === true;
  return (
    <Link
      href="/settings"
      title="The scan engine and the model run inside your environment. Only approved public pages are fetched from the internet."
      className="block rounded-ctl px-2 py-2 transition-colors duration-150 hover:bg-panel"
    >
      <span className="flex items-center gap-2 text-[13px] text-ink">
        <span className={cx("size-1.5 rounded-full", err ? "bg-crit" : caps ? "bg-local shadow-[0_0_0_3px_rgb(94_234_212/0.15)]" : "bg-faint")} />
        {err ? "Engine offline" : caps ? "Engine connected" : "Connecting…"}
      </span>
      <span className="mt-1 block pl-3.5 text-[11.5px] leading-4 text-faint">
        {err ? (
          err.code === "app_not_configured" ? "Set TRACEFOLD_APP_TOKEN" : "Start it with uv run tracefold serve"
        ) : caps ? (
          <>
            <span className={modelUp ? "text-local" : "text-med"}>{modelUp ? "Local model ready" : "Local model unavailable"}</span> · v{caps.engine_version}
          </>
        ) : (
          " "
        )}
      </span>
    </Link>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [crumb, setCrumb] = useState<string | null>(null);
  const isPublic = PUBLIC_PATHS.some((p) => (p === "/" ? path === "/" : path.startsWith(p)));
  if (isPublic) return <>{children}</>;
  return <AppShell path={path} crumb={crumb} setCrumb={setCrumb}>{children}</AppShell>;
}

function AppShell({ path, crumb, setCrumb, children }: { path: string; crumb: string | null; setCrumb: (c: string | null) => void; children: ReactNode }) {
  const state = useWorkspace();
  const counts = useCounts(state.current?.id ?? null);
  if (!state.ready)
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  if (path.startsWith("/onboarding")) return <WorkspaceCtx.Provider value={state}>{children}</WorkspaceCtx.Provider>;

  const section = NAV.find((n) => path.startsWith(n.href)) ?? NAV[0];
  const deep = path.split("/").filter(Boolean).length > 1;

  return (
    <WorkspaceCtx.Provider value={state}>
      <CrumbCtx.Provider value={setCrumb}>
        <div className="flex min-h-screen">
          <aside className="sticky top-0 hidden h-screen w-[232px] shrink-0 flex-col border-r border-line bg-[#0c0c0c] p-2 md:flex">
            <WorkspaceSwitcher state={state} />
            <nav className="mt-4 flex flex-col gap-px" aria-label="Main">
              {NAV.map(({ href, label, icon: Icon }) => {
                const active = path.startsWith(href);
                const badge = href === "/findings" ? counts.open : href === "/actions" ? counts.approvals : null;
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cx(
                      "flex h-8 items-center gap-2.5 rounded-ctl px-2 text-[13px] transition-colors duration-150",
                      active ? "bg-panel-2 text-ink" : "text-mute hover:bg-panel hover:text-ink",
                    )}
                  >
                    <Icon className={cx("size-4", active ? "text-ink" : "text-faint")} aria-hidden />
                    {label}
                    {!!badge && (
                      <span
                        className={cx(
                          "ml-auto min-w-5 rounded-md px-1.5 text-center font-mono text-[11px] leading-5",
                          href === "/actions" ? "bg-accent/15 text-accent" : "bg-crit/15 text-crit",
                        )}
                      >
                        {badge}
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>
            <div className="mt-auto border-t border-line pt-2">
              <EngineStatus />
            </div>
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            <header className="sticky top-0 z-30 flex h-12 shrink-0 items-center justify-between gap-4 border-b border-line bg-bg/85 px-4 backdrop-blur-md sm:px-6">
              <nav className="flex min-w-0 items-center gap-1.5 text-[13px]" aria-label="Breadcrumb">
                <Link href="/" className="wordmark mr-1 text-[11px] text-ink md:hidden">
                  Tracefold
                </Link>
                <Link href={section.href} className={cx("shrink-0", deep ? "text-mute hover:text-ink" : "text-ink")}>
                  {section.label}
                </Link>
                {deep && (
                  <>
                    <ChevronRight className="size-3.5 shrink-0 text-faint" aria-hidden />
                    <span className="truncate text-ink">{crumb ?? "…"}</span>
                  </>
                )}
              </nav>
              <div className="flex items-center gap-2">
                <NewScanButton variant="secondary" />
              </div>
            </header>

            <nav className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2 md:hidden" aria-label="Sections">
              {NAV.map(({ href, label }) => (
                <Link
                  key={href}
                  href={href}
                  className={cx("shrink-0 rounded-ctl px-2.5 py-1.5 text-[13px]", path.startsWith(href) ? "bg-panel-2 text-ink" : "text-mute")}
                >
                  {label}
                </Link>
              ))}
            </nav>

            <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
              {state.error ? <EngineProblem error={state.error} /> : children}
            </main>
          </div>
        </div>
      </CrumbCtx.Provider>
    </WorkspaceCtx.Provider>
  );
}

function EngineProblem({ error }: { error: ApiError }) {
  const setup = error.code === "app_not_configured";
  return (
    <div className="mx-auto mt-16 max-w-lg rounded-card border border-line bg-panel p-7">
      <p className="text-[15px] font-medium text-ink">{setup ? "Connect the app to your engine" : "Can't reach the Tracefold engine"}</p>
      <p className="mt-2 text-sm leading-relaxed text-mute">{error.message}</p>
      <div className="mt-5">
        <LinkButton href="/onboarding" variant="secondary" size="sm">
          Setup steps
        </LinkButton>
      </div>
    </div>
  );
}
