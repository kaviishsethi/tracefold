"""``tracefold-mcp``: run the stdio MCP server, or write its local config."""
from __future__ import annotations

import argparse
import sys

from .config import ConfigError, load_config, write_config


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tracefold-mcp")
    ap.add_argument("--config", help="config file (default: $TRACEFOLD_MCP_CONFIG or ~/.config/tracefold/mcp.json)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="run the MCP server on stdio (default)")
    c = sub.add_parser("configure", help="write the adapter config; reads the client token from stdin")
    c.add_argument("--workspace", required=True)
    c.add_argument("--base-url", default="http://127.0.0.1:8787")
    sub.add_parser("check", help="validate the config and reach the engine")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "configure":
            if sys.stdin.isatty():
                print("Paste the tf_… token from `tracefold add-client`, then press Enter:", file=sys.stderr)
            path = write_config(args.config, args.base_url, sys.stdin.readline(), args.workspace)
            print(f"wrote {path} (mode 600)", file=sys.stderr)
            return 0
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"tracefold-mcp: {e}", file=sys.stderr)
        return 2

    if args.cmd == "check":
        import anyio

        from .engine import EngineClient, EngineError

        async def probe() -> int:
            eng = EngineClient(cfg)
            try:
                ws = await eng.workspaces()
            except EngineError as e:
                print(f"tracefold-mcp: {e.code}: {e.message}", file=sys.stderr)
                return 1
            finally:
                await eng.aclose()
            ids = [w["id"] for w in ws["items"]]
            print(f"engine reachable; granted workspaces: {', '.join(ids) or '(none)'}", file=sys.stderr)
            if cfg.workspace_id not in ids:
                print(f"tracefold-mcp: configured workspace {cfg.workspace_id!r} is not granted", file=sys.stderr)
                return 1
            return 0
        return anyio.run(probe)

    from .server import build_server
    build_server(cfg).run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
