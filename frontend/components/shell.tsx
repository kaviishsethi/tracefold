"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, useWorkspace, ws, type Action, type ApiError, type Page, type Workspace } from "@/lib/api";
import { Spinner, cx } from "./ui";

/** Marketing pages: no engine needed, no app chrome. */
export const PUBLIC_PATHS = ["/", "/manifesto", "/enterprise", "/pricing", "/security", "/contact"];

const NAV = [
  { href: "/scan", label: "Scan" },
  { href: "/findings", label: "Findings" },
  { href: "/actions", label: "Approvals" },
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

function usePendingApprovals(workspaceId: string | null) {
  const [n, setN] = useState(0);
  const path = usePathname();
  useEffect(() => {
    if (!workspaceId) return;
    const load = () =>
      api<Page<Action>>(ws(workspaceId, "/actions?status=drafted&limit=100"))
        .then((p) => setN(p.items.length))
        .catch(() => setN(0));
    load();
    window.addEventListener("tracefold:actions-changed", load);
    return () => window.removeEventListener("tracefold:actions-changed", load);
  }, [path, workspaceId]);
  return n;
}

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const isPublic = PUBLIC_PATHS.some((p) => (p === "/" ? path === "/" : path.startsWith(p)));
  if (isPublic) return <>{children}</>;
  return <AppShell path={path}>{children}</AppShell>;
}

function AppShell({ path, children }: { path: string; children: ReactNode }) {
  const state = useWorkspace();
  const pending = usePendingApprovals(state.current?.id ?? null);
  const setupPage = path.startsWith("/setup");

  return (
    <WorkspaceCtx.Provider value={state}>
      <header className="sticky top-0 z-30 border-b border-line bg-bg/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[960px] items-center gap-6 px-5">
          <Link href="/" className="wordmark text-[12px] text-ink">
            Tracefold
          </Link>
          <nav className="flex items-center gap-1 text-sm" aria-label="Main">
            {NAV.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                aria-current={path.startsWith(href) ? "page" : undefined}
                className={cx(
                  "flex h-8 items-center gap-2 rounded-ctl px-3 transition-colors",
                  path.startsWith(href) ? "bg-panel-2 text-ink" : "text-mute hover:text-ink",
                )}
              >
                {label}
                {href === "/actions" && pending > 0 && (
                  <span className="min-w-5 rounded-md bg-accent px-1.5 text-center text-[11px] font-medium leading-5 text-[#0a0c0c]">{pending}</span>
                )}
              </Link>
            ))}
          </nav>
          {state.list.length > 1 && (
            <select
              aria-label="Workspace"
              value={state.current?.id}
              onChange={(e) => state.select(e.target.value)}
              className="ml-auto h-8 rounded-ctl border border-line bg-panel px-2 text-sm text-ink"
            >
              {state.list.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-[960px] px-5 py-10">
        {!state.ready ? (
          <div className="flex justify-center py-24">
            <Spinner />
          </div>
        ) : state.error && !setupPage ? (
          <NotConnected error={state.error} />
        ) : (
          children
        )}
      </main>
    </WorkspaceCtx.Provider>
  );
}

function NotConnected({ error }: { error: ApiError }) {
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <h1 className="text-xl text-ink">Tracefold isn&apos;t set up yet</h1>
      <p className="mt-2 text-sm text-mute">{error.message}</p>
      <Link href="/setup" className="mt-6 inline-flex h-10 items-center rounded-ctl bg-[#fafafa] px-4 text-sm font-medium text-[#0a0c0c]">
        Set up
      </Link>
    </div>
  );
}
