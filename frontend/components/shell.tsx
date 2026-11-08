"use client";

import Link from "next/link";
import "./app-polish.css";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { CheckCircle2, Globe, LayoutGrid, ScanSearch, ShieldAlert, type LucideIcon } from "lucide-react";
import { api, useWorkspace, ws, type Action, type ApiError, type Finding, type Page, type Workspace } from "@/lib/api";
import { Spinner, Wordmark, cx } from "./ui";

/** Marketing pages: no engine needed, no app chrome. */
export const PUBLIC_PATHS = ["/"];

type Count = "findings" | "approvals";
const NAV: { href: string; label: string; icon: LucideIcon; count?: Count }[] = [
  { href: "/overview", label: "Overview", icon: LayoutGrid },
  { href: "/scan", label: "Scan", icon: ScanSearch },
  { href: "/findings", label: "Findings", icon: ShieldAlert, count: "findings" },
  { href: "/actions", label: "Approvals", icon: CheckCircle2, count: "approvals" },
  { href: "/discovery", label: "Discovery", icon: Globe },
];

interface WorkspaceState {
  list: Workspace[];
  current: Workspace | null;
  error: ApiError | null;
  ready: boolean;
  select: (id: string) => void;
}

const WorkspaceCtx = createContext<WorkspaceState>({ list: [], current: null, error: null, ready: false, select: () => {} });

export function useCurrentWorkspace() {
  return useContext(WorkspaceCtx);
}

/** Open findings and drafted approvals, refreshed on navigation and when an approval changes. */
function useCounts(workspaceId: string | null): Record<Count, number> {
  const [counts, setCounts] = useState<Record<Count, number>>({ findings: 0, approvals: 0 });
  const path = usePathname();
  useEffect(() => {
    if (!workspaceId) return;
    const load = () => {
      api<Page<Finding>>(ws(workspaceId, "/findings?limit=100"))
        .then((p) => setCounts((c) => ({ ...c, findings: p.items.filter((f) => f.status === "open").length })))
        .catch(() => {});
      api<Page<Action>>(ws(workspaceId, "/actions?status=drafted&limit=100"))
        .then((p) => setCounts((c) => ({ ...c, approvals: p.items.length })))
        .catch(() => setCounts((c) => ({ ...c, approvals: 0 })));
    };
    load();
    window.addEventListener("tracefold:actions-changed", load);
    return () => window.removeEventListener("tracefold:actions-changed", load);
  }, [path, workspaceId]);
  return counts;
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const isPublic = PUBLIC_PATHS.some((p) => (p === "/" ? path === "/" : path.startsWith(p)));
  if (isPublic) return <>{children}</>;
  return <AppShell path={path}>{children}</AppShell>;
}

function NavLink({ href, label, icon: Icon, count, active }: { href: string; label: string; icon: LucideIcon; count?: number; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cx(
        "flex h-9 items-center gap-3 rounded-ctl px-3 text-sm transition-colors",
        active ? "bg-panel-2 text-ink" : "text-mute hover:bg-panel hover:text-ink",
      )}
    >
      <Icon className={cx("size-4 shrink-0", active ? "text-accent" : "text-faint")} aria-hidden />
      <span className="flex-1">{label}</span>
      {!!count && (
        <span
          className={cx(
            "min-w-6 rounded-md px-1.5 text-center text-[11px] font-medium leading-5",
            href === "/actions" ? "bg-accent text-[#0a0c0c]" : "bg-raised text-ink-2",
          )}
        >
          {count}
        </span>
      )}
    </Link>
  );
}

function AppShell({ path, children }: { path: string; children: ReactNode }) {
  const state = useWorkspace();
  const counts = useCounts(state.current?.id ?? null);
  const active = (href: string) => path === href || path.startsWith(href + "/");

  return (
    <WorkspaceCtx.Provider value={state}>
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-[248px] shrink-0 flex-col border-r border-line bg-[#0c0f0f] px-3 py-5 md:flex">
          <Link href="/" className="px-3">
            <Wordmark className="text-[12px]" />
          </Link>

          <nav className="mt-6 flex flex-col gap-0.5" aria-label="Main">
            {NAV.map((n) => (
              <NavLink key={n.href} {...n} count={n.count ? counts[n.count] : undefined} active={active(n.href)} />
            ))}
          </nav>

          <div className="mt-auto border-t border-line px-3 pt-3 text-xs">
            {state.error ? (
              <p className="flex items-center gap-2 text-crit">
                <span className="size-1.5 rounded-full bg-crit" /> Engine not reachable
              </p>
            ) : (
              <>
                <p className="flex items-center gap-2 text-mute">
                  <span className="size-1.5 rounded-full bg-accent" /> Local engine connected
                </p>
                {state.list.length > 1 ? (
                  <select
                    aria-label="Workspace"
                    value={state.current?.id}
                    onChange={(e) => state.select(e.target.value)}
                    className="-ml-1 mt-1 w-full bg-transparent text-[13px] text-ink-2 outline-none"
                  >
                    {state.list.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="mt-1 truncate text-[13px] text-ink-2">{state.current?.name}</p>
                )}
                <p className="mt-0.5 text-faint">Shared with your coding assistant</p>
              </>
            )}
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 flex items-center gap-1 overflow-x-auto border-b border-line bg-bg/90 px-4 py-2.5 backdrop-blur md:hidden">
            <Link href="/" className="mr-2 shrink-0">
              <Wordmark className="text-[11px]" />
            </Link>
            {NAV.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={cx("shrink-0 rounded-ctl px-2.5 py-1.5 text-[13px]", active(href) ? "bg-panel-2 text-ink" : "text-mute")}
              >
                {label}
              </Link>
            ))}
          </header>
          <main className="mx-auto w-full max-w-[1200px] px-5 py-8 lg:px-10 lg:py-10">
            {!state.ready ? (
              <div className="flex justify-center py-24">
                <Spinner />
              </div>
            ) : state.error ? (
              <NotConnected error={state.error} />
            ) : (
              children
            )}
          </main>
        </div>
      </div>
    </WorkspaceCtx.Provider>
  );
}

const START = [
  ["Engine", "cd server && uv run tracefold serve --port 8787"],
  ["Web app", "cd frontend && npm run dev"],
];

function NotConnected({ error }: { error: ApiError }) {
  return (
    <div className="mx-auto max-w-xl py-16">
      <h1 className="text-xl text-ink">The engine isn&apos;t reachable</h1>
      <p className="mt-2 text-sm text-mute">{error.message}</p>
      <p className="mt-6 text-sm text-ink-2">Start it from the repository root, then reload this page:</p>
      <ol className="mt-3 space-y-2">
        {START.map(([label, cmd]) => (
          <li key={label} className="rounded-card border border-line bg-panel px-4 py-3">
            <p className="text-xs text-faint">{label}</p>
            <code className="mt-1 block overflow-x-auto whitespace-nowrap font-mono text-[13px] text-ink-2">{cmd}</code>
          </li>
        ))}
      </ol>
      <p className="mt-4 text-sm text-mute">
        First time? <code className="font-mono text-ink-2">uv run tracefold quickstart --root &lt;your project&gt;</code> creates the workspace and tokens. Full steps are in{" "}
        <code className="font-mono text-ink-2">SETUP.md</code>.
      </p>
    </div>
  );
}
