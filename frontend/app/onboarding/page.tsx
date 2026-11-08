"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, Check, Copy, RotateCw } from "lucide-react";
import { api, type ApiError, type Workspace } from "@/lib/api";
import { Button, ImageSlot, LinkButton, Spinner, Wordmark, cx } from "@/components/ui";

const STEPS = ["Engine", "App", "Assistant", "Remediation", "Ready"] as const;

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

function Hint({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-relaxed text-faint">{children}</p>;
}

type Conn = { state: "checking" } | { state: "ok"; list: Workspace[] } | { state: "error"; error: ApiError };

function useConnection() {
  const [conn, setConn] = useState<Conn>({ state: "checking" });
  const check = useCallback(() => {
    setConn({ state: "checking" });
    api<{ items: Workspace[] }>("/workspaces")
      .then(({ items }) => setConn({ state: "ok", list: items }))
      .catch((e: ApiError) => setConn({ state: "error", error: e }));
  }, []);
  useEffect(check, [check]);
  return { conn, check };
}

function ConnectionCard({ conn, onRetry }: { conn: Conn; onRetry: () => void }) {
  const ok = conn.state === "ok" && conn.list.length > 0;
  return (
    <div
      className={cx(
        "rounded-card border p-4 text-[13px]",
        conn.state === "checking" ? "border-line bg-panel" : ok ? "border-local-line bg-local-bg" : "border-med/25 bg-med/10",
      )}
      aria-live="polite"
    >
      <div className="flex items-center justify-between gap-3">
        <span className={cx("inline-flex items-center gap-2 font-medium", conn.state === "checking" ? "text-mute" : ok ? "text-local" : "text-med")}>
          {conn.state === "checking" ? <Spinner className="size-3.5" /> : <span className={cx("size-1.5 rounded-full", ok ? "bg-local" : "bg-med")} />}
          {conn.state === "checking"
            ? "Checking the connection"
            : ok
              ? "App connected to the engine"
              : conn.state === "ok"
                ? "Connected, but no workspace granted"
                : conn.error.code === "app_not_configured"
                  ? "App token not set"
                  : "Can't reach the engine"}
        </span>
        <button onClick={onRetry} className="inline-flex items-center gap-1 text-xs text-mute hover:text-ink">
          <RotateCw className="size-3" aria-hidden /> Check again
        </button>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-ink-2">
        {conn.state === "ok"
          ? conn.list.length
            ? conn.list.map((w) => `${w.name} (${w.id})`).join(", ")
            : "The token works but covers no workspace. Create it with --workspace <id>."
          : conn.state === "error"
            ? conn.error.message
            : " "}
      </p>
    </div>
  );
}

export default function Onboarding() {
  const [step, setStep] = useState(0);
  const { conn, check } = useConnection();
  const wsId = conn.state === "ok" && conn.list[0] ? conn.list[0].id : "ws_main";

  return (
    <div className="grid min-h-screen bg-bg lg:grid-cols-2">
      {/* Left: image + caption */}
      <ImageSlot label="Side image: folded paper with a traced line" className="hidden flex-col justify-between p-10 lg:flex">
        <Link href="/" aria-label="Tracefold home">
          <Wordmark className="text-[15px]" />
        </Link>
        <p className="max-w-sm text-[22px] font-medium leading-[1.3] tracking-[-0.025em] text-white">
          Find your private text on approved public pages, and risky content in your files, with a scan engine that runs on your machine.
        </p>
      </ImageSlot>

      {/* Right: the steps */}
      <div className="flex flex-col bg-[#171717] px-6 py-8 sm:px-12">
        <div className="lg:hidden">
          <Link href="/" aria-label="Tracefold home">
            <Wordmark />
          </Link>
        </div>

        <div className="mx-auto flex w-full max-w-[480px] flex-1 flex-col justify-center py-12">
          <ol className="mb-10 grid grid-cols-5 gap-2" aria-label="Progress">
            {STEPS.map((s, i) => (
              <li key={s}>
                <button onClick={() => setStep(i)} className="flex w-full flex-col gap-2 text-left" aria-current={i === step ? "step" : undefined}>
                  <span className={cx("h-[3px] rounded-full transition-colors duration-500 ease-out-expo", i <= step ? "bg-ink" : "bg-raised")} />
                  <span className={cx("text-xs", i === step ? "text-ink" : "text-faint")}>{s}</span>
                </button>
              </li>
            ))}
          </ol>

          <div key={step} className="rise space-y-4">
            {step === 0 && (
              <>
                <div>
                  <h1 className="text-2xl text-ink">Start the engine</h1>
                  <p className="mt-2 text-sm text-mute">
                    The engine reads your files, runs the checks and keeps the findings. It binds to 127.0.0.1 only. Run these in the engine&apos;s{" "}
                    <code className="font-mono text-ink-2">server/</code> folder.
                  </p>
                </div>
                <CodeBlock
                  code={`uv sync\nexport TRACEFOLD_DATA=$PWD/data\nuv run tracefold init\nuv run tracefold add-workspace ws_main --name "Main" --root /path/to/your/repo`}
                />
                <Hint>
                  <code className="font-mono">--root</code> registers a local Git folder so you can scan changes in place. Leave it out for an uploads-only
                  workspace.
                </Hint>
                <CodeBlock
                  label="token for this app (printed once)"
                  code={`APP_TOKEN=$(uv run tracefold add-client upload-app --workspace ws_main)\necho "$APP_TOKEN"`}
                />
                <CodeBlock label="optional: approved public pages" code={`uv run tracefold add-manifest ws_main sources_main sources.json`} />
                <Hint>
                  The source list format is on the{" "}
                  <Link href="/sources" className="text-ink-2 underline-offset-4 hover:underline">
                    Sources
                  </Link>{" "}
                  page. Without one, you can still scan for potential risks in your files.
                </Hint>
                <CodeBlock code={`uv run tracefold serve --port 8787`} />
                <Button onClick={() => setStep(1)} className="mt-2 w-full">
                  Continue <ArrowRight className="size-4" aria-hidden />
                </Button>
              </>
            )}

            {step === 1 && (
              <>
                <div>
                  <h1 className="text-2xl text-ink">Connect this app</h1>
                  <p className="mt-2 text-sm text-mute">
                    The app&apos;s server holds the token and adds it to every engine request. Your browser never sees it.
                  </p>
                </div>
                <CodeBlock label="frontend/.env.local" code={`TRACEFOLD_ENGINE_URL=http://127.0.0.1:8787\nTRACEFOLD_APP_TOKEN=tf_...`} />
                <Hint>Restart the app after editing .env.local, then check the connection.</Hint>
                <ConnectionCard conn={conn} onRetry={check} />
                <Button onClick={() => setStep(2)} className="w-full">
                  Continue <ArrowRight className="size-4" aria-hidden />
                </Button>
              </>
            )}

            {step === 2 && (
              <>
                <div>
                  <h1 className="text-2xl text-ink">Connect a coding assistant</h1>
                  <p className="mt-2 text-sm text-mute">
                    Optional. The MCP adapter lets an assistant scan its own changes and recheck fixes against the same engine. Its token can&apos;t approve
                    takedowns or key disables.
                  </p>
                </div>
                <CodeBlock
                  code={`cd server\nMCP_TOKEN=$(uv run tracefold add-client mcp-adapter --workspace ${wsId} --caps submit,read,read_evidence,recheck,cancel)\n\ncd ../adapters/mcp && uv sync\necho "$MCP_TOKEN" | uv run tracefold-mcp configure --workspace ${wsId} --base-url http://127.0.0.1:8787\nuv run tracefold-mcp check`}
                />
                <CodeBlock
                  label=".mcp.json"
                  code={`{\n  "mcpServers": {\n    "tracefold": {\n      "command": "uv",\n      "args": ["run", "--directory", "/absolute/path/to/tracefold/adapters/mcp", "tracefold-mcp"]\n    }\n  }\n}`}
                />
                <Hint>
                  If the assistant&apos;s model is cloud-hosted, create its token with <code className="font-mono">--disclosure minimal</code> so it gets no paths,
                  explanations or evidence text.
                </Hint>
                <Button onClick={() => setStep(3)} className="w-full">
                  Continue <ArrowRight className="size-4" aria-hidden />
                </Button>
              </>
            )}

            {step === 3 && (
              <>
                <div>
                  <h1 className="text-2xl text-ink">Set up remediation</h1>
                  <p className="mt-2 text-sm text-mute">
                    Optional. Tracefold drafts takedown requests and AWS key disables after each scan. Nothing is sent or changed until a person approves.
                  </p>
                </div>
                <CodeBlock
                  label="company details and host contacts"
                  code={`uv run tracefold set-remediation-profile ${wsId} --company "Example, Inc." --reply-to legal@example.com\nuv run tracefold add-takedown-contact ${wsId} forum.example.org --email abuse@forum.example.org\nuv run tracefold add-takedown-contact ${wsId} paste.example.net --form-url https://paste.example.net/legal/removal`}
                />
                <CodeBlock
                  label="email delivery (engine environment)"
                  code={`# Default: approved letters are written to $TRACEFOLD_DATA/outbox/*.eml and nothing is sent\nTRACEFOLD_MAIL_TRANSPORT=outbox\n\n# To send for real through Resend:\nTRACEFOLD_MAIL_TRANSPORT=resend\nRESEND_API_KEY=...\nTRACEFOLD_MAIL_FROM=legal@your-verified-domain.com`}
                />
                <CodeBlock
                  label="AWS key disabling (engine environment)"
                  code={`TRACEFOLD_AWS_REMEDIATION_ACCESS_KEY_ID=...\nTRACEFOLD_AWS_REMEDIATION_SECRET_ACCESS_KEY=...`}
                />
                <Hint>
                  Use an IAM principal allowed only <code className="font-mono">iam:GetAccessKeyLastUsed</code> and{" "}
                  <code className="font-mono">iam:UpdateAccessKey</code>. On approval the leaked key is set Inactive. It is never used, and no replacement is
                  created. Restart the engine after changing its environment.
                </Hint>
                <Button onClick={() => setStep(4)} className="w-full">
                  Continue <ArrowRight className="size-4" aria-hidden />
                </Button>
              </>
            )}

            {step === 4 && (
              <>
                <div>
                  <h1 className="text-2xl text-ink">Run your first scan</h1>
                  <p className="mt-2 text-sm text-mute">Upload a few files, or capture changes from the registered folder.</p>
                </div>
                <ConnectionCard conn={conn} onRetry={check} />
                <div className="rounded-card border border-local-line bg-local-bg p-4 text-sm leading-relaxed text-ink-2">
                  <p className="mb-2 font-medium text-local">What leaves your machine</p>
                  <ul className="space-y-1.5">
                    {[
                      "Requests to the public URLs in sources you approved, made by a separate worker",
                      "Calls to Exa or Tavily, only for sources that name them",
                      "Approved takedown emails and AWS key disables, only after a person signs off",
                    ].map((t) => (
                      <li key={t} className="flex gap-2">
                        <Check className="mt-0.5 size-4 shrink-0 text-local" aria-hidden />
                        {t}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-xs text-mute">Your file text is never sent. The Egress page lists every outbound request per scan.</p>
                </div>
                {conn.state === "ok" && conn.list.length > 0 ? (
                  <LinkButton href="/scan" className="w-full">
                    Run first scan <ArrowRight className="size-4" aria-hidden />
                  </LinkButton>
                ) : (
                  <Button className="w-full" disabled>
                    Connect the app first
                  </Button>
                )}
              </>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between text-xs text-faint">
          {step > 0 ? (
            <button onClick={() => setStep(step - 1)} className="inline-flex items-center gap-1.5 hover:text-ink">
              <ArrowLeft className="size-3.5" aria-hidden /> Back
            </button>
          ) : (
            <Link href="/" className="inline-flex items-center gap-1.5 hover:text-ink">
              <ArrowLeft className="size-3.5" aria-hidden /> Back to Tracefold
            </Link>
          )}
          <Link href="/overview" className="hover:text-ink">
            Skip to dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
