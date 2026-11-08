"use client";

import { useEffect, useState } from "react";
import { api, ws, type ApiError } from "@/lib/api";
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
    </div>
  );
}
