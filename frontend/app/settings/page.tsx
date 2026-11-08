"use client";

import { useEffect, useState } from "react";
import { api, ws, type ApiError, type Capabilities } from "@/lib/api";
import { AgentPrompt } from "@/components/agent-prompt";
import { CONNECT_AWS, CONNECT_AWS_PROMPT, CopyCommand } from "@/components/copy-command";
import { useCurrentWorkspace } from "@/components/shell";
import { H1 } from "@/components/bits";
import { Select } from "@/components/select";
import { Button, ErrorNote, Field, inputClass } from "@/components/ui";

interface Company {
  name: string | null;
  website: string | null;
  reply_to: string | null;
  industry: string | null;
}

/** Each industry switches on extra checks for the regulated data it handles. */
const INDUSTRIES: { value: string; label: string; checks: string }[] = [
  { value: "financial", label: "Financial services", checks: "Card numbers, IBANs and bank routing numbers" },
  { value: "healthcare", label: "Healthcare", checks: "Medical record numbers, provider NPIs and dates of birth" },
  { value: "government", label: "Government and public sector", checks: "CUI and FOUO markings and passport numbers" },
  { value: "retail", label: "Retail and e-commerce", checks: "Card numbers" },
  { value: "technology", label: "Technology", checks: "Secrets and personal identifiers (the standard checks)" },
];
const industryLabel = (v: string) => INDUSTRIES.find((i) => i.value === v)?.label ?? "";

const EMPTY = { name: "", website: "", reply_to: "", industry: "" };
const toForm = (c: Company) => ({ name: c.name ?? "", website: c.website ?? "", reply_to: c.reply_to ?? "", industry: c.industry ?? "" });

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
    let alive = true;
    // Retry a few times: the engine can blip (a restart), and an empty form would look like the data was lost.
    const load = async (attempt: number): Promise<void> => {
      try {
        const f = toForm(await api<Company>(ws(workspace.id, "/company")));
        if (!alive) return;
        setSaved(f);
        setForm(f);
        setEditing(!f.name); // nothing saved yet: start in the form
        setLoaded(true);
      } catch (err) {
        if (!alive) return;
        if (attempt < 4) setTimeout(() => load(attempt + 1), 800 * attempt);
        else setError(`Couldn't load settings: ${(err as ApiError).message}`);
      }
    };
    load(1);
    return () => {
      alive = false;
    };
  }, [workspace]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!workspace) return;
    setBusy(true);
    setError(null);
    try {
      const c = await api<Company>(ws(workspace.id, "/company"), {
        method: "PUT",
        json: { name: form.name.trim(), website: form.website.trim() || null, reply_to: form.reply_to.trim(), industry: form.industry || null },
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
    ["Industry", industryLabel(saved.industry)],
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
          <div>
            <span className="mb-1.5 block text-[13px] text-mute">Industry</span>
            <Select
              label="Industry"
              size="md"
              className="w-full"
              disabled={!canEdit}
              value={form.industry || "__none"}
              onChange={(v) => setForm({ ...form, industry: v === "__none" ? "" : v })}
              options={[{ value: "__none", label: "Choose your industry" }, ...INDUSTRIES.map((i) => ({ value: i.value, label: i.label }))]}
            />
            <span className="mt-1.5 block text-xs text-faint">
              {form.industry ? `Also checks for: ${INDUSTRIES.find((i) => i.value === form.industry)?.checks}.` : "Adds checks for the regulated data your industry handles."}
            </span>
          </div>
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
      {loaded && workspace && <SchedulesCard workspaceId={workspace.id} canEdit={canEdit} />}
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

/** The one outside account Tracefold can use: AWS, to turn off leaked keys. */
function ConnectionsCard() {
  const [caps, setCaps] = useState<Capabilities | null>(null);
  useEffect(() => {
    const load = () => api<Capabilities>("/capabilities").then(setCaps).catch(() => {});
    load();
    const t = setInterval(load, 5000); // flips to Connected soon after connect-aws runs
    return () => clearInterval(t);
  }, []);
  if (!caps) return null;
  const aws = caps.remediation?.aws_key_disable === "configured";
  return (
    <section className="mt-6 rounded-card border border-line bg-panel">
      <header className="flex min-h-14 items-center justify-between gap-3 border-b border-line px-5">
        <h2 className="text-sm font-medium text-ink">AWS</h2>
        <span className={`flex items-center gap-2 text-sm ${aws ? "text-ink" : "text-faint"}`}>
          <span className={`size-1.5 rounded-full ${aws ? "bg-local" : "bg-line-strong"}`} />
          {aws ? "Connected" : "Not connected"}
        </span>
      </header>
      {!aws && (
        <div className="flex flex-wrap items-center gap-2 px-5 py-4">
          <div className="min-w-[260px] flex-1">
            <CopyCommand command={CONNECT_AWS} />
          </div>
          <AgentPrompt text={CONNECT_AWS_PROMPT} />
        </div>
      )}
    </section>
  );
}

interface Schedule {
  schedule_id: string;
  name: string;
  every: "hour" | "day" | "week";
  enabled: boolean;
  next_run_at: string;
  last_run_at: string | null;
  last_scan_id: string | null;
  last_error: string | null;
  runs: number;
}

const when = (ts: string | null) => (ts ? new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "");

/** Optional scheduled checks, like scheduled tasks: each re-runs a scan every hour, day or week. */
function SchedulesCard({ workspaceId, canEdit }: { workspaceId: string; canEdit: boolean }) {
  const [items, setItems] = useState<Schedule[] | null>(null);
  const load = () => api<{ items: Schedule[] }>(ws(workspaceId, "/schedules")).then((r) => setItems(r.items)).catch(() => setItems([]));
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);
  const patch = async (id: string, json: object) => {
    await api(ws(workspaceId, `/schedules/${id}`), { method: "PATCH", json }).catch(() => {});
    load();
  };
  const remove = async (id: string) => {
    await api(ws(workspaceId, `/schedules/${id}`), { method: "DELETE" }).catch(() => {});
    load();
  };
  return (
    <section className="mt-6 rounded-card border border-line bg-panel">
      <header className="flex min-h-14 items-center border-b border-line px-5">
        <h2 className="text-sm font-medium text-ink">Scheduled checks</h2>
      </header>
      {items === null ? null : items.length === 0 ? (
        <p className="px-5 py-4 text-sm text-mute">None. Open a finished scan and choose Schedule to re-run it every hour, day or week.</p>
      ) : (
        <ul>
          {items.map((m) => (
            <li key={m.schedule_id} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line px-5 py-3.5 text-sm first:border-t-0">
              <span className="min-w-0 flex-1">
                <span className="block truncate font-mono text-[13px] text-ink">{m.name}</span>
                <span className="block text-xs text-faint">
                  Every {m.every}
                  {m.enabled ? ` · next ${when(m.next_run_at)}` : " · paused"}
                  {m.last_scan_id && (
                    <>
                      {" · "}
                      <a href={`/scan/${m.last_scan_id}`} className="hover:text-ink">
                        last run {when(m.last_run_at)}
                      </a>
                    </>
                  )}
                  {m.last_error && <span className="text-med"> · {m.last_error}</span>}
                </span>
              </span>
              {canEdit && (
                <span className="flex items-center gap-3 text-xs">
                  <button type="button" onClick={() => patch(m.schedule_id, { run_now: true })} className="text-mute hover:text-ink">
                    Run now
                  </button>
                  <button type="button" onClick={() => patch(m.schedule_id, { enabled: !m.enabled })} className="text-mute hover:text-ink">
                    {m.enabled ? "Pause" : "Resume"}
                  </button>
                  <button type="button" onClick={() => remove(m.schedule_id)} className="text-mute hover:text-crit">
                    Delete
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
