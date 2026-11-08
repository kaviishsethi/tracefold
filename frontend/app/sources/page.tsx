"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, Copy, Database, Lock } from "lucide-react";
import { useCurrentWorkspace } from "@/components/shell";
import { PlatformLogos } from "@/components/platforms";
import { Empty, PageHeader, Panel, cx } from "@/components/ui";

function CodeBlock({ code, label }: { code: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="overflow-hidden rounded-ctl border border-line bg-[#0b0b0b]">
      <div className="flex items-center justify-between gap-3 border-b border-line px-3 py-1.5">
        <span className="text-[11px] text-faint">{label ?? "shell"}</span>
        <button onClick={copy} aria-label="Copy" className="rounded-md p-1 text-faint transition-colors hover:bg-raised hover:text-ink">
          {copied ? <Check className="size-3.5 text-ok" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
        </button>
      </div>
      <pre className="scroll-thin overflow-x-auto px-3 py-2.5 font-mono text-xs leading-5 text-ink-2">{code}</pre>
    </div>
  );
}

const MANIFEST_EXAMPLE = `[
  {"source_id": "docs_site", "url": "https://docs.example.com/guide", "provider": "direct"},
  {"source_id": "forum_thread", "url": "https://forum.example.org/t/123", "provider": "exa"},
  {"source_id": "paste", "url": "https://paste.example.net/abc", "provider": "tavily"}
]`;

const PROVIDERS: [string, string][] = [
  ["direct", "The engine's retrieval worker fetches the URL itself."],
  ["exa", "Extracted through Exa. Needs EXA_API_KEY in the engine's environment."],
  ["tavily", "Extracted through Tavily. Needs TAVILY_API_KEY in the engine's environment."],
  ["fixture", "Reads a local test file instead of the web. For demos and tests."],
];

export default function Sources() {
  const { current, list } = useCurrentWorkspace();
  const wsId = current?.id ?? "<workspace>";

  return (
    <div>
      <PageHeader
        title="Sources"
        subtitle="Approved public pages Tracefold compares your files against, and who to contact when a copy turns up. Operators manage both with the engine's CLI."
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0 space-y-6">
          <Panel title="Approved source lists" meta={`${list.length} ${list.length === 1 ? "workspace" : "workspaces"}`}>
            {list.length === 0 ? (
              <div className="px-4 py-12 text-center">
                <p className="text-sm font-medium text-ink">No workspaces</p>
                <p className="mt-1 text-[13px] text-mute">This app&apos;s token doesn&apos;t cover a workspace yet.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-left text-[13px]">
                  <thead className="text-xs text-faint">
                    <tr className="border-b border-line">
                      <th className="px-4 py-2.5 font-normal">Workspace</th>
                      <th className="px-4 py-2.5 font-normal">Source lists</th>
                      <th className="px-4 py-2.5 font-normal">URLs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((w) => (
                      <tr key={w.id} className={cx("border-b border-line last:border-0", w.id === current?.id && "bg-panel-2/60")}>
                        <td className="px-4 py-3 align-top">
                          <span className="inline-flex items-center gap-2.5">
                            <span className="flex size-6 items-center justify-center rounded-md border border-line bg-panel-2">
                              <Database className="size-3.5 text-mute" aria-hidden />
                            </span>
                            <span>
                              <span className="block font-medium text-ink">{w.name}</span>
                              <span className="block font-mono text-[11px] text-faint">{w.id}</span>
                            </span>
                          </span>
                        </td>
                        <td className="px-4 py-3 align-top">
                          {w.manifests.length === 0 ? (
                            <span className="text-mute">None yet</span>
                          ) : (
                            <span className="flex flex-wrap gap-1.5">
                              {w.manifests.map((m) => (
                                <span key={m} className="rounded-md border border-line bg-panel-2 px-1.5 py-0.5 font-mono text-xs text-local">
                                  {m}
                                </span>
                              ))}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 align-top">
                          <span className="inline-flex items-center gap-1.5 text-faint">
                            <Lock className="size-3.5" aria-hidden /> Held by the engine
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="border-t border-line px-4 py-3 text-xs text-faint">
              The engine shares source list IDs with clients, not the URLs inside them. Pick a list when you{" "}
              <Link href="/scan" className="text-ink-2 underline-offset-4 hover:underline">
                start a scan
              </Link>
              .
            </p>
          </Panel>

          <Panel title="Add a source list" bodyClassName="space-y-4 p-4">
            <p className="text-[13px] leading-relaxed text-mute">
              A source list is a JSON file of public URLs you approve for fetching. Each entry has a <code className="font-mono text-ink-2">source_id</code>, a{" "}
              <code className="font-mono text-ink-2">url</code> and a <code className="font-mono text-ink-2">provider</code>. Register it from the engine&apos;s{" "}
              <code className="font-mono text-ink-2">server/</code> folder, then reload this page.
            </p>
            <CodeBlock label="sources.json" code={MANIFEST_EXAMPLE} />
            <CodeBlock code={`uv run tracefold add-manifest ${wsId} sources_main sources.json`} />
            <dl className="divide-y divide-line rounded-ctl border border-line text-[13px]">
              {PROVIDERS.map(([p, d]) => (
                <div key={p} className="flex gap-4 px-3 py-2.5">
                  <dt className="w-16 shrink-0 font-mono text-xs text-ink">{p}</dt>
                  <dd className="text-xs text-mute">{d}</dd>
                </div>
              ))}
            </dl>
          </Panel>

          <Panel title="Where copies tend to appear" bodyClassName="p-6">
            <PlatformLogos />
            <p className="mx-auto mt-6 max-w-lg text-center text-xs leading-relaxed text-faint">
              Tracefold can fetch any public URL you approve. These platforms are examples of where copied text and keys often turn up, not a list of
              built-in integrations.
            </p>
          </Panel>
        </div>

        <div className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          <Panel title="Takedown setup" bodyClassName="space-y-4 p-4">
            <p className="text-[13px] leading-relaxed text-mute">
              For each public exposure, Tracefold drafts a takedown request for a person to approve. It needs your company details and a contact for each
              host. There is no built-in directory of host contacts.
            </p>
            <div>
              <p className="mb-1.5 text-xs text-faint">1. Company details used in every letter</p>
              <CodeBlock code={`uv run tracefold set-remediation-profile ${wsId} \\\n  --company "Example, Inc." --reply-to legal@example.com`} />
            </div>
            <div>
              <p className="mb-1.5 text-xs text-faint">2. A host that takes email</p>
              <CodeBlock code={`uv run tracefold add-takedown-contact ${wsId} forum.example.org \\\n  --email abuse@forum.example.org`} />
            </div>
            <div>
              <p className="mb-1.5 text-xs text-faint">3. A host that only takes its own web form</p>
              <CodeBlock code={`uv run tracefold add-takedown-contact ${wsId} paste.example.net \\\n  --form-url https://paste.example.net/legal/removal`} />
            </div>
            <p className="text-xs leading-relaxed text-faint">
              Form hosts move to &ldquo;submit on the host&apos;s form&rdquo; after approval, with the text prefilled for you to paste.
            </p>
          </Panel>
          <div className="rounded-card border border-local-line bg-local-bg p-4 text-[13px] leading-relaxed text-ink-2">
            <p className="font-medium text-local">What a takedown letter contains</p>
            <p className="mt-1.5">
              The public URL, the copied text as it appears there (with secret-shaped values masked) and your company details. Never the name of your private
              file or any other private text.
            </p>
          </div>
          {!current && (
            <Empty title="No workspace selected">
              Commands show <code className="font-mono">&lt;workspace&gt;</code> until the app can read a workspace.
            </Empty>
          )}
        </div>
      </div>
    </div>
  );
}
