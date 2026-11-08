"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { api, ws, type ApiError, type CompanyProfile, type Page, type PresetCatalog, type QueryPlan } from "@/lib/api";
import { PlanSearches, StatusTag, searchLabel } from "@/components/discovery";
import { relativeTime, shortId } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { Select } from "@/components/select";
import { Checkbox } from "@/components/checkbox";
import { Button, Empty, ErrorNote, Field, Loading, PageHeader, Panel, cx, inputClass } from "@/components/ui";

const PRIVACY = "Search providers get this name and the queries, never your files. Don't enter secret project names.";

function CheckRow({ checked, onChange, children, disabled }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; disabled?: boolean }) {
  return (
    <Checkbox checked={checked} onChange={onChange} disabled={disabled} className="text-[13px]">
      {children}
    </Checkbox>
  );
}

function IdentityForm({ workspaceId, onCreated }: { workspaceId: string; onCreated: (p: CompanyProfile) => void }) {
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [aliases, setAliases] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const aliasList = aliases
    .split(",")
    .map((a) => a.trim())
    .filter(Boolean);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const p = await api<CompanyProfile>(ws(workspaceId, "/company-profiles"), {
        method: "POST",
        json: { display_name: name.trim(), official_domain: domain.trim() || null, public_aliases: aliasList, confirm_public: true },
      });
      setName("");
      setDomain("");
      setAliases("");
      setConfirm(false);
      onCreated(p);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6 border-t border-line p-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Public company name">
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme" maxLength={80} />
        </Field>
        <Field label="Official domain (optional)" hint="A bare hostname, like acme.com">
          <input className={inputClass} value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="acme.com" maxLength={253} />
        </Field>
      </div>
      <Field label="Public aliases (optional)" hint="Up to two, comma separated. A public product name narrows results.">
        <input className={inputClass} value={aliases} onChange={(e) => setAliases(e.target.value)} placeholder="Acme Phone" />
      </Field>
      <CheckRow checked={confirm} onChange={setConfirm}>
        <span className="text-ink-2">This identity is public and may be sent to the selected search providers.</span>
        <span className="mt-0.5 block text-xs text-faint">{PRIVACY}</span>
      </CheckRow>
      <ErrorNote error={error} />
      <Button onClick={submit} loading={busy} disabled={!confirm || name.trim().length < 2 || aliasList.length > 2}>
        Approve identity
      </Button>
    </div>
  );
}

function PlanForm({
  workspaceId,
  profiles,
  catalog,
  onCreated,
}: {
  workspaceId: string;
  profiles: CompanyProfile[];
  catalog: PresetCatalog;
  onCreated: (p: QueryPlan) => void;
}) {
  const [profileId, setProfileId] = useState(profiles[0]?.profile_id ?? "");
  const [mode, setMode] = useState<"pack" | "presets">("pack");
  const [pack, setPack] = useState(catalog.packs[0]?.pack_id ?? "");
  const [chosen, setChosen] = useState<string[]>([]);
  const [providers, setProviders] = useState<string[]>(["exa", "tavily"]);
  const [excludeOwn, setExcludeOwn] = useState(true);
  const [excludeNoise, setExcludeNoise] = useState(true);
  const [experimental, setExperimental] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!profiles.some((p) => p.profile_id === profileId)) setProfileId(profiles[0]?.profile_id ?? "");
  }, [profiles, profileId]);

  const profile = profiles.find((p) => p.profile_id === profileId);
  const current = catalog.presets.filter((p) => p.status !== "legacy");
  const searches = (mode === "pack" ? catalog.packs.find((p) => p.pack_id === pack)?.presets.length ?? 0 : chosen.length) * providers.length;
  const toggle = (list: string[], v: string, on: boolean) => (on ? [...list, v] : list.filter((x) => x !== v));

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const plan = await api<QueryPlan>(ws(workspaceId, "/query-plans"), {
        method: "POST",
        json: {
          profile_id: profileId,
          ...(mode === "pack" ? { pack, include_experimental: experimental } : { presets: chosen }),
          providers,
          scope: { mode: "broad", exclude_official_domain: excludeOwn, exclude_noise: excludeNoise },
        },
      });
      onCreated(plan);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6 border-t border-line p-5">
      <div className="flex flex-wrap items-center gap-3">
        <Select
          label="Identity"
          value={profileId}
          onChange={setProfileId}
          options={profiles.map((p) => ({ value: p.profile_id, label: `${p.display_name}${p.official_domain ? ` · ${p.official_domain}` : ""}` }))}
        />
        <div role="group" aria-label="Plan type" className="flex gap-1">
          {(
            [
              ["pack", "Search packs"],
              ["presets", "Choose searches"],
            ] as const
          ).map(([v, l]) => (
            <button
              key={v}
              aria-pressed={mode === v}
              onClick={() => setMode(v)}
              className={cx("h-8 rounded-md px-2.5 text-xs font-medium transition-colors", mode === v ? "bg-raised text-ink" : "text-mute hover:text-ink")}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      {mode === "pack" ? (
        <div className="space-y-2">
          {catalog.packs.map((p) => (
            <label key={p.pack_id} className={cx("discovery-pack flex cursor-pointer gap-3 rounded-ctl border p-4", pack === p.pack_id ? "border-line-strong bg-raised" : "border-line hover:bg-panel-2")}>
              <input type="radio" name="pack" className="mt-0.5 accent-accent" checked={pack === p.pack_id} onChange={() => setPack(p.pack_id)} />
              <span className="min-w-0">
                <span className="block text-[13px] font-medium text-ink">
                  {searchLabel(p.pack_id)}
                </span>
                <span className="block text-xs text-mute">{p.description}</span>
                <span className="mt-3 flex flex-wrap gap-x-4 gap-y-2">
                  {p.presets.map((id) => (
                    <span key={id} className="inline-flex items-center gap-2 text-xs text-ink-2" title={id}>
                      {searchLabel(id)}{catalog.presets.find((x) => x.preset_id === id)?.status === "experimental" && <StatusTag status="experimental" />}
                    </span>
                  ))}
                </span>
              </span>
            </label>
          ))}
          <CheckRow checked={experimental} onChange={setExperimental}>
            <span className="text-ink-2">Include experimental searches</span>
            <span className="block text-xs text-faint">Experimental searches haven&apos;t found a known copy in testing. By default, packs include only searches that have.</span>
          </CheckRow>
        </div>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {current.map((p) => {
            const missing = p.needs.find((n) => (n === "alias" && !profile?.public_aliases.length) || (n === "domain" && !profile?.official_domain));
            return (
              <li key={p.preset_id}>
                <CheckRow checked={chosen.includes(p.preset_id)} onChange={(v) => setChosen((c) => toggle(c, p.preset_id, v))} disabled={!!missing}>
                  <span className="inline-flex flex-wrap items-center gap-1.5">
                    <span className="text-[13px] text-ink" title={p.preset_id}>{searchLabel(p.preset_id)}</span>
                    {p.status !== "benchmarked" && <StatusTag status={p.status} />}
                  </span>
                  <span className="block text-xs text-mute">{missing ? `Needs a public ${missing}.` : p.description}</span>
                </CheckRow>
              </li>
            );
          })}
        </ul>
      )}

      <div className="flex flex-wrap gap-x-6 gap-y-2">
        {["exa", "tavily"].map((p) => (
          <CheckRow key={p} checked={providers.includes(p)} onChange={(v) => setProviders((c) => toggle(c, p, v))}>
            <span className="font-mono text-xs text-ink-2">{p}</span>
          </CheckRow>
        ))}
        <CheckRow checked={excludeOwn} onChange={setExcludeOwn}>
          <span className="text-xs text-ink-2">Leave out the company&apos;s own site</span>
        </CheckRow>
        <CheckRow checked={excludeNoise} onChange={setExcludeNoise}>
          <span className="text-xs text-ink-2" title={catalog.noise_domains.join(", ")}>
            Leave out {catalog.noise_domains.length} profile and social sites
          </span>
        </CheckRow>
      </div>

      <ErrorNote error={error} />
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={submit} loading={busy} disabled={!profileId || !providers.length || (mode === "presets" && !chosen.length)}>
          Create plan
        </Button>
        <span className="text-xs text-faint">
          Up to {searches} {searches === 1 ? "search" : "searches"}. Limits: 8 searches, 20 pages and 40 provider requests per scan.
        </span>
      </div>
    </div>
  );
}

export default function Discovery() {
  const { current } = useCurrentWorkspace();
  const [catalog, setCatalog] = useState<PresetCatalog | null>(null);
  const [profiles, setProfiles] = useState<CompanyProfile[] | null>(null);
  const [plans, setPlans] = useState<QueryPlan[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showIdentity, setShowIdentity] = useState(false);

  const load = useCallback(async () => {
    if (!current) return;
    try {
      const [c, pr, pl] = await Promise.all([
        api<PresetCatalog>("/query-presets"),
        api<{ items: CompanyProfile[] }>(ws(current.id, "/company-profiles")),
        api<Page<QueryPlan>>(ws(current.id, "/query-plans?limit=100")),
      ]);
      setCatalog(c);
      setProfiles(pr.items);
      setPlans([...pl.items].sort((a, b) => b.created_at.localeCompare(a.created_at)));
    } catch (e) {
      setError((e as ApiError).message);
    }
  }, [current]);

  useEffect(() => {
    load();
  }, [load]);

  const canConfigure = current?.capabilities.includes("configure") ?? false;
  const byProfile = useMemo(() => new Map((profiles ?? []).map((p) => [p.profile_id, p])), [profiles]);

  if (error) return <ErrorNote error={error} />;
  if (!current) return <Empty title="No workspace">This app&apos;s token doesn&apos;t cover a workspace yet.</Empty>;
  if (!catalog || !profiles || !plans) return <Loading />;

  return (
    <div>
      <PageHeader
        title="Company discovery"
        subtitle="Find possible copies of your files using your company’s public name"
      />
      {!canConfigure && (
        <p className="mb-4 rounded-ctl border border-med/25 bg-med/10 px-3.5 py-2.5 text-sm text-med">
          This app&apos;s grant for {current.name} doesn&apos;t include <code className="font-mono">configure</code>, so it can use approved plans but can&apos;t
          approve identities or create plans.
        </p>
      )}

      <div className="grid gap-6">
        <div className="min-w-0 space-y-6">
          <Panel
            title="Approved identities"
            meta={`${profiles.length}`}
            actions={
              canConfigure && profiles.length > 0 ? (
                <button onClick={() => setShowIdentity((v) => !v)} className="text-xs text-mute hover:text-ink">
                  {showIdentity ? "Close" : "Approve another"}
                </button>
              ) : undefined
            }
          >
            {profiles.length === 0 ? (
              <p className="px-4 py-4 text-[13px] text-mute">No public identity approved yet.</p>
            ) : (
              <ul className="divide-y divide-line">
                {profiles.map((p) => (
                  <li key={p.profile_id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3 text-[13px]">
                    <span className="font-medium text-ink">{p.display_name}</span>
                    {p.official_domain && <span className="font-mono text-xs text-ink-2">{p.official_domain}</span>}
                    {p.public_aliases.length > 0 && <span className="text-xs text-mute">aka {p.public_aliases.join(", ")}</span>}
                    <span className="ml-auto text-xs text-faint">
                      v{p.version} · approved {relativeTime(p.approved_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {canConfigure && (profiles.length === 0 || showIdentity) && (
              <IdentityForm
                workspaceId={current.id}
                onCreated={() => {
                  setShowIdentity(false);
                  load();
                }}
              />
            )}
          </Panel>

          <Panel title="Query plans" meta={`${plans.length}`}>
            {plans.length === 0 ? (
              <p className="px-4 py-4 text-[13px] text-mute">No plans yet.</p>
            ) : (
              <ul className="divide-y divide-line">
                {plans.map((p) => (
                  <li key={p.query_plan_id}>
                    <button
                      onClick={() => setOpen((o) => (o === p.query_plan_id ? null : p.query_plan_id))}
                      aria-expanded={open === p.query_plan_id}
                      className="group flex w-full items-center gap-3 px-4 py-3 text-left text-[13px] transition-colors hover:bg-panel-2"
                    >
                      <ChevronRight className={cx("size-4 shrink-0 text-faint transition-transform", open === p.query_plan_id && "rotate-90")} aria-hidden />
                      <span className="font-medium text-ink">{p.display_name}</span>
                      <span className="min-w-0 flex-1 truncate text-mute">
                        {p.pack ? searchLabel(p.pack) : [...new Set(p.searches.map((s) => searchLabel(s.template_id)))].join(", ")} · {p.searches.length}{" "}
                        {p.searches.length === 1 ? "search" : "searches"}
                      </span>
                      <span className="hidden font-mono text-xs text-faint sm:inline" title={p.query_plan_id}>{shortId(p.query_plan_id)}</span>
                      <span className="shrink-0 text-xs text-faint">{relativeTime(p.created_at)}</span>
                    </button>
                    {open === p.query_plan_id && (
                      <div className="border-t border-line bg-panel-2/40">
                        <PlanSearches plan={p} />
                        {p.omitted_presets.length > 0 && (
                          <p className="border-t border-line px-4 py-2.5 text-xs text-faint">
                            Left out: {p.omitted_presets.map((o) => `${o.preset} (${o.reason})`).join("; ")}
                          </p>
                        )}
                        <div className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3 text-xs text-faint">
                          <span>
                            Identity v{p.profile_version}
                            {byProfile.get(p.profile_id)?.version !== p.profile_version ? " (an older version)" : ""} · own site{" "}
                            {p.scope.exclude_official_domain === false ? "included" : "left out"}
                          </span>
                          <Link href={`/scan?plan=${encodeURIComponent(p.query_plan_id)}`} className="ml-auto inline-flex items-center gap-1 text-ink-2 hover:text-ink">
                            Scan with this plan
                          </Link>
                        </div>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {canConfigure &&
              (profiles.length > 0 ? (
                <PlanForm
                  workspaceId={current.id}
                  profiles={profiles}
                  catalog={catalog}
                  onCreated={(p) => {
                    setOpen(p.query_plan_id);
                    load();
                  }}
                />
              ) : (
                <p className="border-t border-line px-4 py-3 text-xs text-faint">Approve an identity first.</p>
              ))}
          </Panel>
        </div>

      </div>
    </div>
  );
}
