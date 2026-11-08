"""Operator CLI. Provisioning happens here, never over HTTP."""
from __future__ import annotations

import argparse
import json
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
    rp.add_argument("--company", required=True, help='legal name, e.g. "Northwind Relay, Inc."')
    rp.add_argument("--reply-to", required=True, help="email the host should reply to")

    tc = sub.add_parser("add-takedown-contact", help="where takedown requests for a public host are sent")
    tc.add_argument("workspace")
    tc.add_argument("host", help="bare hostname, e.g. forum.example")
    g = tc.add_mutually_exclusive_group(required=True)
    g.add_argument("--email", help="the host's abuse/legal address (sent automatically on approval)")
    g.add_argument("--form-url", help="the host's own removal form (prefilled request, submitted by a person)")

    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=8787)

    o = sub.add_parser("export-openapi")
    o.add_argument("out")

    args = ap.parse_args(argv)
    from .envfile import load_env_file
    loaded = load_env_file()
    if loaded and args.cmd == "serve":
        print(f"loaded from .env: {', '.join(sorted(loaded))}", file=sys.stderr)
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
