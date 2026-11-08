"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Check } from "lucide-react";
import { Button, Field, cx, inputClass } from "./ui";

const TOPICS = [
  { id: "enterprise", label: "Enterprise", hint: "Deployments, pricing and walkthroughs" },
  { id: "support", label: "Support", hint: "Setup, scans and findings" },
  { id: "security", label: "Security", hint: "Reporting a vulnerability" },
] as const;
type Topic = (typeof TOPICS)[number]["id"];

export function ContactForm() {
  const params = useSearchParams();
  const initial = TOPICS.some((t) => t.id === params.get("topic")) ? (params.get("topic") as Topic) : "enterprise";
  const [topic, setTopic] = useState<Topic>(initial);
  const [form, setForm] = useState({ email: "", name: "", company: "", role: "", message: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
    setError(null);
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await fetch("/api/contact", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ topic, ...form }) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail ?? "Something went wrong. Please try again.");
      setSent(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (sent)
    return (
      <div className="flex min-h-[520px] flex-col items-start justify-center rounded-[24px] border border-line bg-[#090a0c] p-[clamp(28px,4vw,48px)]">
        <span className="flex size-10 items-center justify-center rounded-full border border-ok/30 bg-ok/10 text-ok">
          <Check className="size-5" aria-hidden />
        </span>
        <h2 className="mt-6 text-[26px] font-medium tracking-[-0.03em] text-ink">Thanks, we&apos;ll be in touch.</h2>
        <p className="mt-2 max-w-md text-[15px] leading-[1.6] text-mute">We reply within one business day, to {form.email}.</p>
      </div>
    );

  return (
    <form onSubmit={submit} noValidate className="rounded-[24px] border border-line bg-[#090a0c] p-[clamp(24px,4vw,44px)]">
      <fieldset>
        <legend className="mb-4 text-[15px] font-medium text-ink">What brings you here?</legend>
        <div role="radiogroup" className="grid gap-2 sm:grid-cols-3">
          {TOPICS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="radio"
              aria-checked={topic === t.id}
              onClick={() => setTopic(t.id)}
              className={cx(
                "rounded-ctl border p-3.5 text-left transition-colors duration-150",
                topic === t.id ? "border-accent/60 bg-accent/10" : "border-line hover:border-line-strong",
              )}
            >
              <span className="block text-[14px] font-medium text-ink">{t.label}</span>
              <span className="mt-0.5 block text-xs text-mute">{t.hint}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <Field label="Work email">
          <input type="email" required autoComplete="email" value={form.email} onChange={set("email")} className={inputClass} />
        </Field>
        <Field label="Name">
          <input required autoComplete="name" value={form.name} onChange={set("name")} className={inputClass} />
        </Field>
        <Field label="Company">
          <input autoComplete="organization" value={form.company} onChange={set("company")} className={inputClass} />
        </Field>
        <Field label="Role">
          <input autoComplete="organization-title" value={form.role} onChange={set("role")} className={inputClass} />
        </Field>
      </div>
      <div className="mt-4">
        <Field label="What should we know?">
          <textarea rows={5} required value={form.message} onChange={set("message")} className={cx(inputClass, "h-auto resize-y py-2.5")} />
        </Field>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        <p role="alert" aria-live="polite" className="min-h-5 text-[13px] leading-5 text-crit">
          {error}
        </p>
        <Button type="submit" loading={busy} disabled={!form.email || !form.name || !form.message}>
          Send message
        </Button>
      </div>
    </form>
  );
}
