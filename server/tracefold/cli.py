"""Operator CLI. Provisioning happens here, never over HTTP."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import Settings
from .contracts.enums import Capability


def _engine(args):
    from .engine import Engine
    s = Settings()
    if args.data:
        s.data_dir = Path(args.data).resolve()
    s.start_runner = False
    return Engine(s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tracefold")
    ap.add_argument("--data", help="data directory (default: $TRACEFOLD_DATA or ./data)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create/migrate the database")

    w = sub.add_parser("add-workspace")
    w.add_argument("id")
    w.add_argument("--name", required=True)
    w.add_argument("--root", help="registered local directory (omit for upload-only)")
    w.add_argument("--exclude", action="append", default=[])

    c = sub.add_parser("add-client", help="create a client and print its token once")
    c.add_argument("name")
    c.add_argument("--workspace", action="append", required=True, help="workspace id (repeatable)")
    c.add_argument("--caps", default=",".join(x.value for x in Capability))
    c.add_argument("--disclosure", choices=["full", "minimal"], default="full")

    m = sub.add_parser("add-manifest")
    m.add_argument("workspace")
    m.add_argument("manifest_id")
    m.add_argument("file", help="JSON file: list of {source_id, url, provider[, fixture_path]}")

    rp = sub.add_parser("set-remediation-profile", help="company details used to sign takedown requests")
    rp.add_argument("workspace")
    rp.add_argument("--company", required=True, help='legal name, e.g. "Halyard Freight, Inc."')
    rp.add_argument("--reply-to", required=True, help="email the host should reply to")

    tc = sub.add_parser("add-takedown-contact", help="where takedown requests for a public host are sent")
    tc.add_argument("workspace")
    tc.add_argument("host", help="bare hostname, e.g. pastebin.com")
    g = tc.add_mutually_exclusive_group(required=True)
    g.add_argument("--email", help="the host's abuse/legal address (sent automatically on approval)")
    g.add_argument("--form-url", help="the host's own removal form (prefilled request, submitted by a person)")

    q = sub.add_parser("quickstart", help="set everything up for a local folder in one step (safe to re-run)")
    q.add_argument("--root", required=True, help="the folder to protect (a Git repo works best)")
    q.add_argument("--workspace", help="workspace id (default: derived from the folder name)")
    q.add_argument("--name", help="display name (default: the folder name)")
    q.add_argument("--port", type=int, default=8787, help="port the engine will serve on")
    q.add_argument("--public-url", action="append", default=[], help="a public page to check for copies (repeatable)")
    q.add_argument("--frontend-env", help="where to write the web app config (default: frontend/.env.local)")
    q.add_argument("--mcp-config", help="where to write the MCP adapter config (default: ~/.config/tracefold/mcp.json)")
    q.add_argument("--company", help="your company's public name: signs takedowns and seeds a discovery plan")
    q.add_argument("--domain", help="your company's public domain, left out of discovery results (optional)")
    q.add_argument("--reply-to", help="email takedown recipients should reply to (sets the takedown signer)")
    q.add_argument("--json", action="store_true", help="print the result as JSON")

    ca = sub.add_parser("connect-aws", help="let Tracefold turn off leaked AWS keys (uses your AWS CLI login)")
    ca.add_argument("--profile", help="AWS CLI profile to use (default: your default profile)")
    ca.add_argument("--user", default="tracefold-remediation", help="IAM user to create or reuse")
    ca.add_argument("--rotate", action="store_true", help="replace the key already in server/.env")

    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=8787)

    o = sub.add_parser("export-openapi")
    o.add_argument("out")

    args = ap.parse_args(argv)
    from .envfile import load_env_file
    loaded = load_env_file()
    if loaded and args.cmd == "serve":
        print(f"loaded from .env: {', '.join(sorted(loaded))}", file=sys.stderr)
    if args.cmd == "connect-aws":
        from . import connect_aws
        env_path = Path(os.environ.get("TRACEFOLD_ENV_FILE", Path.cwd() / ".env"))
        try:
            for step in connect_aws.run(env_path, args.profile, args.user, args.rotate):
                print(step)
        except connect_aws.ConnectError as ex:
            print(f"tracefold connect-aws: {ex}", file=sys.stderr)
            return 1
        print("Done. Approve a key shut-off in the app; the engine picks up the key without a restart.")
        return 0
    if args.cmd == "serve":
        import uvicorn
        from .api.app import create_app
        from .engine import Engine
        s = Settings()
        if args.data:
            s.data_dir = Path(args.data).resolve()
        uvicorn.run(create_app(Engine(s)), host="127.0.0.1", port=args.port, log_level="info")
        return 0
    e = _engine(args)
    if args.cmd == "init":
        print(f"database ready at {e.settings.db_path}")
    elif args.cmd == "add-workspace":
        root = str(Path(args.root).resolve()) if args.root else None
        e.add_workspace(args.id, args.name, root, args.exclude)
        print(f"workspace {args.id} registered")
    elif args.cmd == "add-client":
        caps = [Capability(x.strip()) for x in args.caps.split(",") if x.strip()]
        token = e.add_client(args.name, {ws: (caps, args.disclosure) for ws in args.workspace})
        print("Store this token now; it is not shown again.", file=sys.stderr)
        print(token)
    elif args.cmd == "add-manifest":
        sources = json.loads(Path(args.file).read_text())
        v = e.add_manifest(args.workspace, args.manifest_id, sources)
        print(f"manifest {args.manifest_id} v{v}")
    elif args.cmd == "quickstart":
        from . import quickstart
        r = quickstart.run(e, args.root, args.workspace, args.name, args.port, args.public_url, args.frontend_env,
                           args.mcp_config, company=args.company, domain=args.domain, reply_to=args.reply_to)
        print(json.dumps(r, indent=2) if args.json else quickstart.describe(r))
    elif args.cmd == "set-remediation-profile":
        e.set_remediation_profile(args.workspace, args.company, args.reply_to)
        print(f"remediation profile set for {args.workspace}")
    elif args.cmd == "add-takedown-contact":
        e.add_takedown_contact(args.workspace, args.host, args.email, args.form_url)
        print(f"takedown contact for {args.host} saved")
    elif args.cmd == "export-openapi":
        from .api.app import create_app
        Path(args.out).write_text(json.dumps(create_app(e).openapi(), indent=2) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
