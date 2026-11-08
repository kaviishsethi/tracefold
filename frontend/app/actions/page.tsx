"use client";

import { useEffect, useState } from "react";
import { api, ws, type Action, type ApiError, type Page } from "@/lib/api";
import { useCurrentWorkspace } from "@/components/shell";
import { ActionCard } from "@/components/action-card";
import { Disclosure, H1 } from "@/components/bits";
import { ErrorNote } from "@/components/ui";

export default function Approvals() {
  const { current: workspace } = useCurrentWorkspace();
  const [actions, setActions] = useState<Action[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspace) return;
    api<Page<Action>>(ws(workspace.id, "/actions?limit=100"))
      .then((p) => setActions(p.items))
      .catch((e: ApiError) => (e.status === 404 ? setActions([]) : setError(e.message)));
  }, [workspace]);

  if (!workspace) return null;
  const update = (a: Action) => setActions((list) => (list ?? []).map((x) => (x.action_id === a.action_id ? a : x)));
  const pending = (actions ?? []).filter((a) => a.status === "drafted" || a.status === "failed" || a.status === "awaiting_manual_submission");
  const done = (actions ?? []).filter((a) => !pending.includes(a));

  return (
    <div>
      <H1 sub="Takedowns and leaked-key fixes Tracefold has drafted. Nothing happens until you approve.">Approvals</H1>
      <ErrorNote error={error} />
      {actions === null && !error && <p className="text-sm text-mute">Loading…</p>}
      {actions && pending.length === 0 && <p className="text-sm text-mute">Nothing needs your approval.</p>}
      <div className="space-y-4">
        {pending.map((a) => (
          <ActionCard key={a.action_id} action={a} workspaceId={workspace.id} workspaceName={workspace.name} onChange={update} />
        ))}
      </div>
      {done.length > 0 && (
        <Disclosure label={`${done.length} done`} className="mt-10">
          <div className="mt-4 space-y-4">
            {done.map((a) => (
              <ActionCard key={a.action_id} action={a} workspaceId={workspace.id} workspaceName={workspace.name} onChange={update} />
            ))}
          </div>
        </Disclosure>
      )}
    </div>
  );
}
