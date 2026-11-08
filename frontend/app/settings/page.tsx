"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";
import { api, type ApiError, type Capabilities } from "@/lib/api";
import { bytes } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { ErrorNote, Loading, PageHeader, Panel, cx } from "@/components/ui";

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

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-6 px-5 py-3">
      <dt className="shrink-0 text-[13px] text-faint">{k}</dt>
      <dd className="min-w-0 text-right text-[13px] text-ink-2">{children}</dd>
    </div>
  );
}

function Chips({ items, mono = true }: { items: string[]; mono?: boolean }) {
  if (!items.length) return <span className="text-faint">None</span>;
  return (
    <span className="flex flex-wrap justify-end gap-1.5">
      {items.map((i) => (
        <span key={i} className={cx("rounded-md border border-line bg-panel-2 px-1.5 py-0.5 text-xs text-ink-2", mono && "font-mono")}>
          {i}
        </span>
      ))}
    </span>
  );
}

const LIMIT_FORMAT: Record<string, (n: number) => string> = {
  max_file_bytes: bytes,
  max_request_bytes: bytes,
  scan_deadline_seconds: (n) => `${Math.round(n / 60)} min`,
  capture_ttl_seconds: (n) => `${Math.round(n / 60)} min`,
};

const DELIVERY: Record<string, string> = {
  outbox: "Outbox: approved letters are written as .eml files and not sent",
  resend: "Resend: approved letters are emailed",
  resend_not_configured: "Resend selected, but RESEND_API_KEY or TRACEFOLD_MAIL_FROM is missing",
};

const MCP_JSON = `{
  "mcpServers": {
    "tracefold": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/tracefold/adapters/mcp", "tracefold-mcp"]
    }
  }
}`;

export default function SettingsPage() {
  const { list } = useCurrentWorkspace();
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Capabilities>("/capabilities")
      .then(setCaps)
      .catch((e: ApiError) => setError(e.message));
  }, []);

  const wsId = list[0]?.id ?? "<workspace>";

  return (
    <div className="max-w-3xl">
      <PageHeader title="Settings" subtitle="How this app is connected to your Tracefold engine, and what the engine reports about itself. Read-only: operators change these with the engine's CLI and environment." />

      <div className="space-y-6">
        <Panel title="Engine" meta={caps ? `v${caps.engine_version}` : undefined}>
          {error ? (
            <div className="p-5">
              <ErrorNote error={error} />
            </div>
          ) : !caps ? (
            <Loading />
          ) : (
            <dl className="divide-y divide-line">
              <Row k="Checks">
                <Chips items={caps.checks} />
              </Row>
              <Row k="Supported inputs">
                <Chips items={caps.supported_inputs} mono={false} />
              </Row>
              <Row k={`Local risk rules (${caps.local_risk_rules.length})`}>
                <Chips items={caps.local_risk_rules} />
              </Row>
              <Row k="Local model">
                {caps.model.available ? (
                  <span className="text-local">
                    Ready · <span className="font-mono text-xs">{String(caps.model.model_id ?? caps.model.model ?? "")}</span>
                  </span>
                ) : (
                  <span className="text-med">
                    Unavailable{caps.model.reason ? ` · ${caps.model.reason}` : ""}
                    {caps.model.model ? <span className="block font-mono text-xs text-faint">{String(caps.model.model)}</span> : null}
                  </span>
                )}
              </Row>
              <Row k="Takedown delivery">{DELIVERY[caps.remediation?.takedown_delivery ?? ""] ?? caps.remediation?.takedown_delivery ?? "Not reported"}</Row>
              <Row k="AWS key disabling">
                {caps.remediation?.aws_key_disable === "configured" ? "Configured" : <span className="text-mute">Not configured</span>}
              </Row>
            </dl>
          )}
        </Panel>

        {caps && (
          <Panel title="Limits">
            <dl className="grid sm:grid-cols-2 [&>div]:border-b [&>div]:border-line">
              {Object.entries(caps.limits).map(([k, v]) => (
                <Row key={k} k={k.replace(/_/g, " ")}>
                  <span className="font-mono text-xs">{(LIMIT_FORMAT[k] ?? String)(v)}</span>
                </Row>
              ))}
            </dl>
          </Panel>
        )}

        {caps && (
          <Panel title="This app's access" meta="per workspace">
            {Object.keys(caps.client_capabilities).length === 0 ? (
              <p className="px-5 py-4 text-[13px] text-mute">This token has no workspace grants.</p>
            ) : (
              <dl className="divide-y divide-line">
                {Object.entries(caps.client_capabilities).map(([w, c]) => {
                  const meta = list.find((x) => x.id === w);
                  return (
                    <Row
                      key={w}
                      k={meta ? `${meta.name} · ${meta.disclosure} disclosure` : w}
                    >
                      <Chips items={c} />
                    </Row>
                  );
                })}
              </dl>
            )}
            <p className="border-t border-line px-5 py-3 text-xs text-faint">
              <code className="font-mono">approve</code> lets this app sign takedowns and key disables. Leave it out of grants for coding assistants.
            </p>
          </Panel>
        )}

        <Panel title="Connect this app" bodyClassName="space-y-3 p-5">
          <p className="text-[13px] leading-relaxed text-mute">
            The browser never holds the engine token. The app&apos;s server adds it to every request. Set both values in{" "}
            <code className="font-mono text-ink-2">frontend/.env.local</code> and restart the app.
          </p>
          <CodeBlock
            label="frontend/.env.local"
            code={`TRACEFOLD_ENGINE_URL=http://127.0.0.1:8787\nTRACEFOLD_APP_TOKEN=tf_...   # from: uv run tracefold add-client upload-app --workspace ${wsId}`}
          />
        </Panel>

        <Panel title="Coding assistants (MCP)" bodyClassName="space-y-3 p-5">
          <p className="text-[13px] leading-relaxed text-mute">
            The MCP adapter lets an assistant scan changes and recheck fixes against the same engine. Give it its own token, without{" "}
            <code className="font-mono text-ink-2">approve</code>.
          </p>
          <CodeBlock
            code={`cd server\nMCP_TOKEN=$(uv run tracefold add-client mcp-adapter --workspace ${wsId} --caps submit,read,read_evidence,recheck,cancel)\n\ncd ../adapters/mcp\nuv sync\necho "$MCP_TOKEN" | uv run tracefold-mcp configure --workspace ${wsId} --base-url http://127.0.0.1:8787\nuv run tracefold-mcp check`}
          />
          <CodeBlock label=".mcp.json" code={MCP_JSON} />
        </Panel>

        <Panel title="Privacy" bodyClassName="space-y-3 p-5 text-[13px] leading-relaxed text-mute">
          <p>
            <span className="font-medium text-ink">Full disclosure</span> returns file paths, model explanations and evidence text.{" "}
            <span className="font-medium text-ink">Minimal disclosure</span> withholds paths, free-text explanations and evidence text.
          </p>
          <p>
            Use minimal disclosure for any assistant whose model is cloud-hosted. Tool results go to that model, and finding titles, rule IDs and coverage
            still leave the machine.
          </p>
          <CodeBlock code={`uv run tracefold add-client cloud-assistant --workspace ${wsId} --caps submit,read,recheck --disclosure minimal`} />
          <p className="text-xs text-faint">
            Private files stay in the engine&apos;s memory and are dropped on restart. Public pages are fetched by a separate worker that only receives source
            list entries. The model endpoint must be on loopback.
          </p>
        </Panel>
      </div>
    </div>
  );
}
