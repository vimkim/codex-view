import json
import threading

import pytest

from codex_view.server import make_server
from codex_view.sessions import SessionCatalog


def record(text, role="assistant", phase="final_answer"):
    return {
        "type": "response_item",
        "timestamp": "2026-01-01T12:00:00Z",
        "payload": {
            "type": "message",
            "role": role,
            "phase": phase,
            "content": [
                {"type": "output_text" if role == "assistant" else "input_text", "text": text}
            ],
        },
    }


def append(path, item):
    with path.open("ab") as stream:
        stream.write(json.dumps(item, ensure_ascii=False).encode() + b"\n")


@pytest.fixture
def corpus(tmp_path):
    home = tmp_path / "codex"
    project = tmp_path / "project"
    other = tmp_path / "other"
    project.mkdir()
    other.mkdir()
    directory = home / "sessions" / "2026" / "01" / "01"
    directory.mkdir(parents=True)

    def create(sid="session-one", cwd=None, source="cli", prompt="Teach me probability"):
        path = directory / f"rollout-{sid}.jsonl"
        append(
            path,
            {
                "type": "session_meta",
                "payload": {
                    "id": sid,
                    "cwd": str(cwd or project),
                    "source": source,
                },
            },
        )
        append(path, record("# AGENTS.md instructions for /example\nPRIVATE CONTEXT", "user", ""))
        append(path, record(prompt, "user", ""))
        return path

    return home, project, other, create


@pytest.fixture
def running_viewer(corpus):
    home, project, _, create = corpus
    path = create()
    append(path, record(r"The mean: \(\frac{\sigma}{\sqrt{n}}\)."))
    session = SessionCatalog(home).discover(project)[0]
    server, live = make_server(session, "0.0.0.0", 0, interval=0.03)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", path, server
    live.close()
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
