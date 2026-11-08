"use client";

import { useEffect, useState } from "react";
import { api, ws, type ApiError, type Capabilities } from "@/lib/api";
import { AgentPrompt } from "@/components/agent-prompt";
import { CONNECT_AWS, CONNECT_AWS_PROMPT, CopyCommand } from "@/components/copy-command";
import { useCurrentWorkspace } from "@/components/shell";
import { H1 } from "@/components/bits";
import { Button, ErrorNote, Field, inputClass } from "@/components/ui";

interface Company {
  name: string | null;
  website: string | null;
  reply_to: string | null;
}

const EMPTY = { name: "", website: "", reply_to: "" };
const toForm = (c: Company) => ({ name: c.name ?? "", website: c.website ?? "", reply_to: c.reply_to ?? "" });

/** The company, set once: searched for in every public check and used to sign takedown requests.
 *  Shows the saved values; Edit opens the form, Save or Cancel closes it. */
export default function SettingsPage() {
  const { current: workspace } = useCurrentWorkspace();
  const [saved, setSaved] = useState(EMPTY);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canEdit = workspace?.capabilities.includes("configure") ?? false;

  useEffect(() => {
    if (!workspace) return;
    api<Company>(ws(workspace.id, "/company"))
      .then((c) => {
        const f = toForm(c);
        setSaved(f);
        setForm(f);
        setEditing(!f.name); // nothing saved yet: start in the form
      })
      .catch(() => setEditing(true))
      .finally(() => setLoaded(true));
  }, [workspace]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!workspace) return;
    setBusy(true);
    setError(null);
    try {
      const c = await api<Company>(ws(workspace.id, "/company"), {
        method: "PUT",
        json: { name: form.name.trim(), website: form.website.trim() || null, reply_to: form.reply_to.trim() },
      });
      const f = toForm(c);
      setSaved(f);
      setForm(f);
      setEditing(false);
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const rows: [string, string][] = [
    ["Company name", saved.name],
    ["Website", saved.website],
    ["Reply-to email", saved.reply_to],
  ];

  return (
    <div className="max-w-xl">
      <H1>Settings</H1>
      <ErrorNote error={error} />
      {!loaded ? null : !editing ? (
        <section className="rounded-card border border-line bg-panel">
          <header className="flex min-h-14 items-center justify-between gap-3 border-b border-line pl-5 pr-3">
            <h2 className="text-sm font-medium text-ink">Company</h2>
            {canEdit && (
              <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
          </header>
          <dl>
            {rows.map(([label, value]) => (
              <div key={label} className="flex items-center justify-between gap-6 border-t border-line px-5 py-3.5 text-sm first:border-t-0">
                <dt className="text-mute">{label}</dt>
                <dd className={value ? "truncate text-ink" : "text-faint"}>{value || "Not set"}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : (
        <form onSubmit={save} className="space-y-5 rounded-card border border-line bg-panel p-5">
          <Field label="Company name">
            <input className={inputClass} value={form.name} onChange={set("name")} disabled={!canEdit} placeholder="Your company" required autoFocus />
          </Field>
          <Field label="Website">
            <input className={inputClass} value={form.website} onChange={set("website")} disabled={!canEdit} placeholder="yourcompany.com" />
          </Field>
          <Field label="Reply-to email" hint="Takedown requests are signed with the company name and ask hosts to reply here.">
            <input type="email" className={inputClass} value={form.reply_to} onChange={set("reply_to")} disabled={!canEdit} placeholder="legal@yourcompany.com" required />
          </Field>
          {canEdit ? (
            <div className="flex items-center gap-2">
              <Button type="submit" size="sm" loading={busy} className="!bg-accent !text-[#0a0c0c]">
                Save
              </Button>
              {saved.name && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setForm(saved);
                    setError(null);
                    setEditing(false);
                  }}
                >
                  Cancel
                </Button>
              )}
            </div>
          ) : (
            <p className="text-sm text-mute">This app&apos;s token can&apos;t change settings. Re-run tracefold quickstart.</p>
          )}
        </form>
      )}
      {loaded && workspace && <SitesCard workspaceId={workspace.id} canEdit={canEdit} />}
      {loaded && <ConnectionsCard />}
    </div>
  );
}

interface Sites {
  always_check: string[];
  never_fetch: string[];
}

const lines = (t: string) => t.split(/[\n,]/).map((x) => x.trim()).filter(Boolean);

/** Pages checked in every public scan, and sites never fetched. Same view/edit pattern as the company card. */
function SitesCard({ workspaceId, canEdit }: { workspaceId: string; canEdit: boolean }) {
  const [sites, setSites] = useState<Sites>({ always_check: [], never_fetch: [] });
  const [form, setForm] = useState({ always: "", never: "" });
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Sites>(ws(workspaceId, "/sites")).then(setSites).catch(() => {});
  }, [workspaceId]);

  function edit() {
    setForm({ always: sites.always_check.join("\n"), never: sites.never_fetch.join("\n") });
    setError(null);
    setEditing(true);
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const next = await api<Sites>(ws(workspaceId, "/sites"), {
        method: "PUT",
        json: { always_check: lines(form.always), never_fetch: lines(form.never) },
      });
      setSites(next);
      setEditing(false);
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  const list = (items: string[]) =>
    items.length ? (
      <ul className="space-y-1 text-right">
        {items.map((x) => (
          <li key={x} className="truncate font-mono text-[13px] text-ink">
            {x}
          </li>
        ))}
      </ul>
    ) : (
      <span className="text-faint">None</span>
    );

  return (
    <section className="mt-6 rounded-card border border-line bg-panel">
      <header className="flex min-h-14 items-center justify-between gap-3 border-b border-line pl-5 pr-3">
        <h2 className="text-sm font-medium text-ink">Sites</h2>
        {canEdit && !editing && (
          <Button size="sm" variant="secondary" onClick={edit}>
            Edit
          </Button>
        )}
      </header>
      {!editing ? (
        <dl>
          {([["Always check", sites.always_check], ["Never fetch", sites.never_fetch]] as const).map(([label, items]) => (
            <div key={label} className="flex items-start justify-between gap-6 border-t border-line px-5 py-3.5 text-sm first:border-t-0">
              <dt className="shrink-0 text-mute">{label}</dt>
              <dd className="min-w-0">{list(items)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <form onSubmit={save} className="space-y-5 p-5">
          <ErrorNote error={error} />
          <Field label="Always check" hint="Pages compared in every public check, even when search finds nothing. One per line.">
            <textarea
              rows={4}
              className={`${inputClass} h-auto py-2 font-mono text-[13px]`}
              value={form.always}
              onChange={(e) => setForm({ ...form, always: e.target.value })}
              placeholder="https://community.yourcompany.com/forum"
            />
          </Field>
          <Field label="Never fetch" hint="Sites Tracefold won't download, including their subdomains. One per line.">
            <textarea
              rows={3}
              className={`${inputClass} h-auto py-2 font-mono text-[13px]`}
              value={form.never}
              onChange={(e) => setForm({ ...form, never: e.target.value })}
              placeholder="yourcompany.com"
            />
          </Field>
          <div className="flex items-center gap-2">
            <Button type="submit" size="sm" loading={busy} className="!bg-accent !text-[#0a0c0c]">
              Save
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}

/** What Tracefold can do on its own when it finds a leaked key, and the one step that turns on what's missing. */
function ConnectionsCard() {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  useEffect(() => {
    const load = () => api<Capabilities>("/capabilities").then(setCaps).catch(() => {});
    load();
    const t = setInterval(load, 5000); // shows AWS as connected soon after connect-aws runs
    return () => clearInterval(t);
  }, []);
  if (!caps) return null;
  const r = caps.remediation ?? {};
  const aws = r.aws_key_disable === "configured";
  const Row = ({ label, ok, children }: { label: string; ok: boolean; children: React.ReactNode }) => (
    <div className="border-t border-line px-5 py-3.5 text-sm first:border-t-0">
      <div className="flex items-center justify-between gap-6">
        <span className="text-mute">{label}</span>
        <span className={`flex items-center gap-2 ${ok ? "text-ink" : "text-faint"}`}>
          <span className={`size-1.5 rounded-full ${ok ? "bg-local" : "bg-line-strong"}`} />
          {ok ? "Ready" : "Not connected"}
        </span>
      </div>
      {children}
    </div>
  );
  return (
    <section className="mt-6 rounded-card border border-line bg-panel">
      <header className="flex min-h-14 items-center border-b border-line px-5">
        <h2 className="text-sm font-medium text-ink">Connections</h2>
      </header>
      <div>
        <Row label="GitHub tokens" ok={r.github_token_revoke === "available"}>
          <p className="mt-1 text-xs text-faint">Revoked through GitHub. Nothing to set up.</p>
        </Row>
        <Row label="AWS keys" ok={aws}>
          {aws ? (
            <p className="mt-1 text-xs text-faint">Leaked keys are turned off in IAM after you approve.</p>
          ) : (
            <div className="mt-3 space-y-2">
              <p className="text-xs text-faint">Run once. It uses your AWS CLI login and creates a user that can only turn keys off.</p>
              <div className="flex flex-wrap items-center gap-2">
                <div className="min-w-[260px] flex-1">
                  <CopyCommand command={CONNECT_AWS} />
                </div>
                <AgentPrompt text={CONNECT_AWS_PROMPT} />
              </div>
            </div>
          )}
        </Row>
      </div>
    </section>
  );
}
