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

/** The company, set once: searched for in every public check and used to sign takedown requests. */
export default function SettingsPage() {
  const { current: workspace } = useCurrentWorkspace();
  const [form, setForm] = useState({ name: "", website: "", reply_to: "" });
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canEdit = workspace?.capabilities.includes("configure") ?? false;

  useEffect(() => {
    if (!workspace) return;
    api<Company>(ws(workspace.id, "/company"))
      .then((c) => setForm({ name: c.name ?? "", website: c.website ?? "", reply_to: c.reply_to ?? "" }))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, [workspace]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!workspace) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const c = await api<Company>(ws(workspace.id, "/company"), {
        method: "PUT",
        json: { name: form.name.trim(), website: form.website.trim() || null, reply_to: form.reply_to.trim() },
      });
      setForm({ name: c.name ?? "", website: c.website ?? "", reply_to: c.reply_to ?? "" });
      setSaved(true);
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setSaved(false);
    setForm({ ...form, [k]: e.target.value });
  };

  return (
    <div className="max-w-xl">
      <H1>Settings</H1>
      <ErrorNote error={error} />
      <form onSubmit={save} className="space-y-5 rounded-card border border-line bg-panel p-5">
        <Field label="Company name">
          <input className={inputClass} value={form.name} onChange={set("name")} disabled={!loaded || !canEdit} placeholder="Your company" required />
        </Field>
        <Field label="Website">
          <input className={inputClass} value={form.website} onChange={set("website")} disabled={!loaded || !canEdit} placeholder="yourcompany.com" />
        </Field>
        <Field label="Reply-to email" hint="Takedown requests are signed with the company name and ask hosts to reply here.">
          <input
            type="email"
            className={inputClass}
            value={form.reply_to}
            onChange={set("reply_to")}
            disabled={!loaded || !canEdit}
            placeholder="legal@yourcompany.com"
            required
          />
        </Field>
        {canEdit ? (
          <div className="flex items-center gap-3">
            <Button type="submit" size="sm" loading={busy} className="!bg-accent !text-[#0a0c0c]">
              Save
            </Button>
            {saved && <span className="text-sm text-local">Saved</span>}
          </div>
        ) : (
          loaded && <p className="text-sm text-mute">This app&apos;s token can&apos;t change settings. Re-run tracefold quickstart.</p>
        )}
      </form>
    </div>
  );
}
