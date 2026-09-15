"""The installed codex-view command."""

import argparse
import json
import os
import signal
import socket
import sys
from pathlib import Path

from . import __version__
from .network import listening_urls
from .picker import choose_session
from .server import make_server
from .sessions import SessionCatalog, clean_label


def parser():
    result = argparse.ArgumentParser(
        description="Select a local Codex conversation and view it live in a browser.",
        epilog="Run in a project directory, or use --all. Ctrl+C stops the server.",
    )
    result.add_argument("session_id", nargs="?", help="session ID (or unique ID prefix)")
    result.add_argument(
        "--last", action="store_true", help="view the most recently updated session"
    )
    result.add_argument("--all", action="store_true", help="show sessions from all directories")
    result.add_argument("-C", "--cd", type=Path, help="filter sessions for this directory")
    result.add_argument(
        "--codex-home", type=Path, help="Codex data directory (default: CODEX_HOME or ~/.codex)"
    )
    result.add_argument(
        "--include-non-interactive", action="store_true", help="include exec and subagent sessions"
    )
    result.add_argument(
        "--host",
        default="0.0.0.0",
        help="listen address (default: 0.0.0.0 for LAN/VPN access; 127.0.0.1 for local only)",
    )
    result.add_argument(
        "--port", type=int, default=8765, help="listen port (default: 8765; 0 chooses a free port)"
    )
    result.add_argument("--list", action="store_true", help="list matching sessions and exit")
    result.add_argument("--json", action="store_true", help="JSON output for --list")
    result.add_argument("--version", action="version", version=f"codex-view {__version__}")
    return result


def main():
    argument_parser = parser()
    args = argument_parser.parse_args()
    if args.last and args.session_id:
        argument_parser.error("choose either SESSION_ID or --last")
    if args.json and not args.list:
        argument_parser.error("--json requires --list")
    if not 0 <= args.port <= 65535:
        argument_parser.error("--port must be between 0 and 65535")
    cwd = (args.cd or Path.cwd()).expanduser().resolve()
    if not cwd.is_dir():
        argument_parser.error(f"not a directory: {cwd}")
    home = args.codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    catalog = SessionCatalog(home)
    if not (catalog.home / "sessions").is_dir():
        argument_parser.error(f"no session directory at {catalog.home / 'sessions'}")

    # Explicit IDs intentionally bypass directory and interactive-session filters.
    def load():
        return catalog.discover(
            None if args.all or args.session_id else cwd,
            args.include_non_interactive or bool(args.session_id),
        )

    sessions = load()
    if args.session_id:
        exact = [session for session in sessions if session.id == args.session_id]
        sessions = exact or [
            session for session in sessions if session.id.startswith(args.session_id)
        ]
        if len(sessions) > 1:
            argument_parser.error("session ID prefix is ambiguous; use a longer prefix")
    if args.list:
        if args.json:
            print(
                json.dumps(
                    [
                        {
                            "id": item.id,
                            "title": item.title,
                            "cwd": str(item.cwd),
                            "updated": item.updated,
                        }
                        for item in sessions
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            for item in sessions:
                print(f"{item.id}  {item.title}  [{clean_label(str(item.cwd))}]")
        return 0
    if not sessions:
        argument_parser.error("no matching sessions; try --all or a different --codex-home")
    if args.last or args.session_id:
        selected = sessions[0]
    else:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            argument_parser.error(
                "interactive selection needs a terminal; use --last or SESSION_ID"
            )
        try:
            selected = choose_session(load, sessions)
        except (KeyboardInterrupt, EOFError):
            return 0
        if selected is None:
            return 0
    try:
        server, live = make_server(selected, args.host, args.port)
    except OSError as error:
        print(f"codex-view: cannot listen on {args.host}:{args.port}: {error}", file=sys.stderr)
        print("Choose another --port if a viewer is already running.", file=sys.stderr)
        return 1
    port = server.server_address[1]
    print(f"Viewing: {selected.title}\nSession: {selected.id}", flush=True)
    print(f"Listening: {args.host}:{port}", flush=True)
    dual_stack = server.address_family == socket.AF_INET6 and not server.socket.getsockopt(
        socket.IPPROTO_IPV6, socket.IPV6_V6ONLY
    )
    print("Available addresses:", flush=True)
    for url in listening_urls(server.server_address[0], port, dual_stack=dual_stack):
        print(f"  {url}", flush=True)
    print("Live updates enabled. Keep chatting in Codex CLI. Ctrl+C stops this viewer.", flush=True)

    def stop(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nViewer stopped.")
    finally:
        signal.signal(signal.SIGTERM, previous)
        live.close()
        server.server_close()
    return 0
