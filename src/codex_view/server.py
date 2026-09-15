"""Serve bundled assets and stream updates for exactly one selected session."""

import json
import mimetypes
import socket
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import unquote, urlsplit

from .sessions import Session
from .transcript import Transcript


class LiveSession:
    def __init__(self, session: Session, interval: float = 1):
        self.session = session
        self.transcript = Transcript(session.path)
        self.interval = interval
        self.condition = threading.Condition()
        self.stop_event = threading.Event()
        self.revision = 0
        self.events: deque[tuple[int, str, dict]] = deque(maxlen=128)
        self.transcript.poll()
        self.worker = threading.Thread(target=self._watch, daemon=True)
        self.worker.start()

    def snapshot(self):
        # Callers hold condition while copying a consistent state.
        return {
            "id": self.session.id,
            "title": self.session.title,
            "cwd": str(self.session.cwd),
            "generation": self.transcript.generation,
            "available": self.transcript.available,
            "messages": list(self.transcript.messages),
        }

    def _watch(self):
        while not self.stop_event.wait(self.interval):
            with self.condition:
                previous = self.transcript.available
                reset, added = self.transcript.poll()
                if reset:
                    kind, data = "snapshot", self.snapshot()
                elif added:
                    kind, data = (
                        "append",
                        {
                            "generation": self.transcript.generation,
                            "messages": added,
                            "available": self.transcript.available,
                        },
                    )
                elif previous != self.transcript.available:
                    kind, data = "status", {"available": self.transcript.available}
                else:
                    continue
                self.revision += 1
                self.events.append((self.revision, kind, data))
                self.condition.notify_all()

    def close(self):
        self.stop_event.set()
        with self.condition:
            self.condition.notify_all()
        self.worker.join(timeout=3)


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True


def make_server(session: Session, host: str, port: int, interval: float = 1):
    assets = files("codex_view").joinpath("static")
    live = LiveSession(session, interval)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def send_headers(self, status, content_type, length=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "; ".join(
                    [
                        "default-src 'self'",
                        "script-src 'self'",
                        "style-src 'self' 'unsafe-inline'",
                        "img-src 'self' data:",
                        "font-src 'self' data:",
                        "connect-src 'self'",
                        "object-src 'none'",
                        "base-uri 'none'",
                        "frame-ancestors 'none'",
                    ]
                ),
            )
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.end_headers()

        def body(self, body, content_type, status=200):
            self.send_headers(status, content_type, len(body))
            if self.command != "HEAD":
                self.wfile.write(body)

        def event(self, revision, kind, data):
            text = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
            self.wfile.write(f"id: {revision}\nevent: {kind}\ndata: {text}\n\n".encode())
            self.wfile.flush()

        def stream(self):
            self.connection.settimeout(20)
            self.send_headers(200, "text/event-stream; charset=utf-8")
            try:
                # Reconnects always receive an authoritative snapshot. This also
                # closes the gap between loading a page and subscribing to updates.
                with live.condition:
                    revision, snapshot = live.revision, live.snapshot()
                self.event(revision, "snapshot", snapshot)
                while not live.stop_event.is_set():
                    with live.condition:
                        live.condition.wait_for(
                            lambda seen=revision: live.revision != seen or live.stop_event.is_set(),
                            timeout=10,
                        )
                        if live.stop_event.is_set():
                            break
                        if live.events and revision < live.events[0][0] - 1:
                            pending = [(live.revision, "snapshot", live.snapshot())]
                        else:
                            pending = [event for event in live.events if event[0] > revision]
                    for seq, kind, data in pending:
                        self.event(seq, kind, data)
                        revision = seq
                    if not pending:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionError, TimeoutError):
                pass
            finally:
                self.close_connection = True

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == "/api/events" and self.command != "HEAD":
                self.stream()
                return
            if path == "/api/session":
                with live.condition:
                    body = json.dumps(live.snapshot(), ensure_ascii=True).encode()
                self.body(body, "application/json; charset=utf-8")
                return
            name = "index.html" if path == "/" else path.lstrip("/")
            parts = name.split("/")
            allowed = name in ("index.html", "style.css", "app.js", "mathjax-config.js")
            if not allowed and not name.startswith("mathjax/"):
                self.body(b"Not found", "text/plain", 404)
                return
            if any(part in ("", ".", "..") or "\\" in part or "\x00" in part for part in parts):
                self.body(b"Not found", "text/plain", 404)
                return
            try:
                body = assets.joinpath(*parts).read_bytes()
            except (OSError, ValueError):
                self.body(b"Not found", "text/plain", 404)
                return
            mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
            self.body(body, mime)

        do_HEAD = do_GET

        def log_message(self, fmt, *args):
            if len(args) > 1 and str(args[1]) != "200":
                super().log_message(fmt, *args)

    server_class = ViewerServer
    if ":" in host:

        class IPv6Server(ViewerServer):
            address_family = socket.AF_INET6

        server_class = IPv6Server
    try:
        server = server_class((host, port), Handler)
    except OSError:
        live.close()
        raise
    return server, live
