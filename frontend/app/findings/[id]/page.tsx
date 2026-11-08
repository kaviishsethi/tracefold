"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  RECHECK_LABEL, api, isTerminal, uploadFiles, ws, type Action, type ApiError, type Evidence, type FindingDetail, type Page, type Recheck,
  type RecheckAccepted, type Scan,
} from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { ActionCard } from "@/components/action-card";
import { Crumbs, Disclosure, Dot, findingPlace } from "@/components/bits";
import { AgentPrompt, findingPrompt } from "@/components/agent-prompt";
import { Upload } from "lucide-react";
import { Button, ErrorNote, Spinner } from "@/components/ui";

function Text({ label, meta, text }: { label: string; meta?: string; text: string | null }) {
  return (
    <div className="min-w-0 rounded-card border border-line bg-panel">
      <div className="flex justify-between gap-3 border-b border-line px-4 py-2 text-xs text-faint">
        <span className="truncate">{label}</span>
        {meta && <span className="shrink-0">{meta}</span>}
      </div>
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap px-4 py-3 font-mono text-[13px] leading-relaxed text-ink-2">{text ?? "Not available."}</pre>
    </div>
  );
}

/** The facts behind a finding: how much matched, how the page was found and retrieved, and which scan saw it. */
function EvidenceFacts({ ev }: { ev: Evidence }) {
  const p = ev.public;
  const origin = p?.discovery_origins?.[0];
  const facts: [string, ReactNode][] = [];
  if (ev.kind === "public_match") {
    if (ev.matched_tokens != null)
      facts.push([
        "Overlap",
        `${ev.matched_tokens} matching words${ev.segment_coverage != null ? `, ${Math.round(ev.segment_coverage * 100)}% of the passage` : ""}`,
      ]);
    if (p)
      facts.push([
        "Found by",
        origin ? `Search · ${origin.provider} ${origin.query_id} · result #${origin.rank}` : p.mode === "discovered" ? "Search" : "Registered source list",
      ]);
    if (p)
      facts.push([
        "Retrieved",
        `${p.retrieved_at ? relativeTime(p.retrieved_at) : "time unknown"}${p.provider ? ` via ${p.provider}` : ""} · ${p.freshness === "cached" ? "saved snapshot" : "live request during the scan"}`,
      ]);
  }
  if (!facts.length) return null;
  return (
    <div className="mt-4">
      <dl className="grid gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-[120px_1fr]">
        {facts.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-faint">{k}</dt>
            <dd className="text-ink-2">{v}</dd>
          </div>
        ))}
      </dl>
      {ev.kind === "public_match" && (
        <p className="mt-3 text-xs text-faint">A match shows the text is public, not that it was published without permission.</p>
      )}
    </div>
  );
}

export default function FindingPage() {
  const { id } = useParams<{ id: string }>();
  const { current: workspace } = useCurrentWorkspace();
  const [f, setF] = useState<FindingDetail | null>(null);
  const [ev, setEv] = useState<Evidence | null>(null);
  const [actions, setActions] = useState<Action[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [recheck, setRecheck] = useState<Recheck | null>(null);
  const file = useRef<HTMLInputElement>(null);

  const load = async (wsId: string) => {
    const d = await api<FindingDetail>(ws(wsId, `/findings/${id}`));
    setF(d);
    const ref = d.latest?.evidence[0];
    if (ref) api<Evidence>(ws(wsId, `/evidence/${ref.evidence_id}`)).then(setEv).catch(() => setEv(null));
    api<Page<Action>>(ws(wsId, `/actions?finding_id=${id}`)).then((p) => setActions(p.items)).catch(() => setActions([]));
    return d;
  };

  useEffect(() => {
    if (workspace) load(workspace.id).catch((e: ApiError) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace, id]);

  async function checkAgain(list: FileList | null) {
    if (!workspace || !list?.length) return;
    setChecking(true);
    setError(null);
    setRecheck(null);
    try {
      const inp = await uploadFiles(workspace.id, Array.from(list));
      const acc = await api<RecheckAccepted>(ws(workspace.id, `/findings/${id}/rechecks`), { method: "POST", json: { input_id: inp.input_id } });
      for (let i = 0; i < 120; i++) {
        const s = await api<Scan>(ws(workspace.id, `/scans/${acc.scan_id}`));
        if (isTerminal(s.state)) break;
        await new Promise((r) => setTimeout(r, 1000));
      }
      const d = await load(workspace.id);
      setRecheck(d.rechecks.find((r) => r.recheck_id === acc.recheck_id) ?? null);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setChecking(false);
      if (file.current) file.current.value = "";
    }
  }

  if (error && !f) return <ErrorNote error={error} />;
  if (!f || !workspace)
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    );

  const o = f.latest;
  const isPublic = f.kind === "public_exposure";

  return (
    <div>
      <Crumbs trail={[["/findings", "Findings"]]} />

      <div className="mb-8">
        <h1 className="flex items-center gap-3 text-2xl tracking-[-0.03em] text-ink">
          <Dot severity={o?.severity} />
          {o?.title ?? "Finding"}
        </h1>
        <p className="mt-1.5 text-sm text-mute">
          <span className="font-mono text-[13px]">{findingPlace(f) || "Location withheld"}</span>
          {o?.scan_id && (
            <>
              {" · "}
              <Link href={`/scan/${o.scan_id}`} className="hover:text-ink">
                {relativeTime(o.created_at)}
              </Link>
            </>
          )}
          {f.status !== "open" && <span className="text-local"> · {f.status === "no_longer_observed" ? "No longer found on the page" : "Not found after the fix"}</span>}
        </p>
      </div>

      <ErrorNote error={error} />

      {ev && (
        <div className={isPublic ? "grid gap-3 md:grid-cols-2" : ""}>
          <Text label={isPublic ? "Your file" : (ev.location.path ?? "Your file")} text={
              ev.availability === "withheld_by_policy"
                ? "Hidden for this client."
                : ev.availability === "evidence_unavailable"
                  ? "Uploaded text is held only in the engine's memory and isn't kept on disk. The engine has restarted since this scan, so the text is gone. Scan the file again to compare side by side."
                  : ev.local_text
            } />
          {isPublic && ev.public && <Text label={ev.public.url} text={ev.public_text} />}
        </div>
      )}

      {ev && <EvidenceFacts ev={ev} />}

      {actions.length > 0 && (
        <section className="mt-8 space-y-4">
          <h2 className="text-sm font-medium text-ink">Ready for your approval</h2>
          {actions.map((a) => (
            <ActionCard
              key={a.action_id}
              action={a}
              workspaceId={workspace.id}
              workspaceName={workspace.name}
              onChange={(n) => setActions((l) => l.map((x) => (x.action_id === n.action_id ? n : x)))}
            />
          ))}
        </section>
      )}

      {f.status === "open" && (
        <section className="mt-8 rounded-card border border-line bg-panel p-5">
          <h2 className="text-sm font-medium text-ink">Fix</h2>
          <p className="mt-1.5 max-w-2xl text-[15px] leading-relaxed text-ink-2">
            {o?.suggested_fix ?? (isPublic ? "Check whether this was meant to be public. Any takedown drafted for it is above." : o?.claim)}
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <AgentPrompt text={findingPrompt(f, ev?.public?.url)} />
            {!isPublic && (
              <>
                <input ref={file} type="file" hidden onChange={(e) => checkAgain(e.target.files)} />
                <Button variant="secondary" size="sm" loading={checking} onClick={() => file.current?.click()}>
                  <Upload className="size-3.5" aria-hidden /> Recheck fixed file
                </Button>
              </>
            )}
          </div>
          {recheck?.outcome && (
            <p className="mt-3 text-sm text-ink">
              {RECHECK_LABEL[recheck.outcome]}
              {recheck.outcome === "inconclusive" && recheck.reason ? ` (${recheck.reason.replaceAll("_", " ")})` : ""}.
            </p>
          )}
        </section>
      )}

      {(o?.conditions || o?.uncertainty || (o?.suggested_fix && o?.claim)) && (
        <Disclosure label="More detail" className="mt-10">
          <div className="mt-3 max-w-2xl space-y-2 leading-relaxed">
            {o?.suggested_fix && o?.claim && <p className="text-ink-2">{o.claim}</p>}
            {o?.conditions && <p>{o.conditions}</p>}
            {o?.uncertainty && <p>{o.uncertainty}</p>}
            {o?.verification_step && <p>{o.verification_step}</p>}
            <p className="text-faint">
              Seen in {f.observations.length} {f.observations.length === 1 ? "scan" : "scans"}, rechecked {f.rechecks.length} {f.rechecks.length === 1 ? "time" : "times"}.
            </p>
          </div>
        </Disclosure>
      )}
    </div>
  );
}
