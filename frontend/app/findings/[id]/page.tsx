"use client";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  RECHECK_LABEL, api, isTerminal, uploadFiles, ws, type Action, type ApiError, type Evidence, type FindingDetail, type Page, type Recheck,
  type RecheckAccepted, type Scan,
} from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { ActionCard } from "@/components/action-card";
import { Crumbs, Disclosure, Dot, findingPlace } from "@/components/bits";
import { AgentPrompt, findingPrompt } from "@/components/agent-prompt";
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
      <Crumbs trail={[["/findings", "Findings"]]} current={o?.title ?? "Finding"} />

      <div className="mb-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <h1 className="flex items-center gap-3 text-2xl tracking-[-0.03em] text-ink">
            <Dot severity={o?.severity} />
            {o?.title ?? "Finding"}
          </h1>
          {f.status === "open" && <AgentPrompt text={findingPrompt(f, ev?.public?.url)} />}
        </div>
        <p className="mt-1 text-sm text-mute">
          {findingPlace(f) || "Location withheld"}
          {f.status !== "open" && <span className="text-local"> · {f.status === "no_longer_observed" ? "No longer found on the page" : "Not found after the fix"}</span>}
        </p>
        {o?.claim && <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-ink-2">{o.claim}</p>}
      </div>

      <ErrorNote error={error} />

      {ev && (
        <div className={isPublic ? "grid gap-3 md:grid-cols-2" : ""}>
          <Text label={`Your file${ev.location.path ? ` · ${ev.location.path}` : ""}`} text={ev.availability === "withheld_by_policy" ? "Hidden for this client." : ev.local_text} />
          {isPublic && ev.public && <Text label={ev.public.url} meta={`fetched ${relativeTime(ev.public.retrieved_at)}`} text={ev.public_text} />}
        </div>
      )}

      {o?.suggested_fix && (
        <section className="mt-8">
          <h2 className="mb-2 text-sm font-medium text-ink">How to fix</h2>
          <p className="max-w-2xl text-[15px] leading-relaxed text-ink-2">{o.suggested_fix}</p>
        </section>
      )}

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
        <section className="mt-8">
          <h2 className="mb-2 text-sm font-medium text-ink">Fixed it?</h2>
          <p className="mb-3 text-sm text-mute">
            {isPublic ? "Public copies are rechecked by scanning the page again." : "Upload the edited file and Tracefold checks this one problem again."}
          </p>
          {!isPublic && (
            <>
              <input ref={file} type="file" hidden onChange={(e) => checkAgain(e.target.files)} />
              <Button variant="secondary" size="sm" loading={checking} onClick={() => file.current?.click()}>
                Upload the fixed file
              </Button>
            </>
          )}
          {recheck?.outcome && (
            <p className="mt-3 text-sm text-ink">
              {RECHECK_LABEL[recheck.outcome]}
              {recheck.outcome === "inconclusive" && recheck.reason ? ` (${recheck.reason.replaceAll("_", " ")})` : ""}.
            </p>
          )}
        </section>
      )}

      {(o?.conditions || o?.uncertainty) && (
        <Disclosure label="More detail" className="mt-10">
          <div className="mt-3 max-w-2xl space-y-2 leading-relaxed">
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
