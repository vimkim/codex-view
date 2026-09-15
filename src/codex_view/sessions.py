"""Discover sessions without coupling the UI to Codex's on-disk layout."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def clean_label(value: str) -> str:
    """Keep terminal control characters out of displayed metadata."""
    return " ".join("".join(c if c.isprintable() else " " for c in value).split())


def text_content(payload: dict) -> str:
    content = payload.get("content", [])
    if not isinstance(content, list):
        return ""
    return "\n\n".join(
        part["text"]
        for part in content
        if isinstance(part, dict)
        and part.get("type") in ("input_text", "output_text", "text")
        and isinstance(part.get("text"), str)
    )


def is_context(text: str) -> bool:
    return text.lstrip().startswith(
        ("# AGENTS.md instructions for ", "<environment_context>", "<permissions instructions>")
    )


@dataclass(frozen=True)
class Session:
    id: str
    path: Path
    cwd: Path
    title: str
    updated: float
    source: str


class SessionCatalog:
    def __init__(self, home: Path):
        self.home = home.expanduser().resolve()
        self._cache: dict[Path, tuple[tuple[int, int], dict, str]] = {}

    def _titles(self) -> dict[str, tuple[str, float]]:
        titles = {}
        try:
            with (self.home / "session_index.jsonl").open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(item, dict):
                        continue
                    sid, name = item.get("id"), item.get("thread_name")
                    if not isinstance(sid, str) or not isinstance(name, str):
                        continue
                    try:
                        updated = datetime.fromisoformat(
                            str(item.get("updated_at", "")).replace("Z", "+00:00")
                        ).timestamp()
                    except (ValueError, TypeError, OverflowError):
                        updated = 0
                    if sid not in titles or updated >= titles[sid][1]:
                        titles[sid] = (clean_label(name), updated)
        except (OSError, UnicodeError):
            pass
        return titles

    def _metadata(self, path: Path, identity: tuple[int, int]) -> tuple[dict, str]:
        cached = self._cache.get(path)
        if cached and cached[0] == identity and cached[2]:
            return cached[1], cached[2]
        metadata, title = {}, ""
        with path.open("rb") as stream:
            # Bound work on a corrupt or unusually large transcript. Later messages
            # are read by the follower, not the picker.
            for _ in range(128):
                line = stream.readline(2 * 1024 * 1024)
                if not line:
                    break
                if not line.endswith(b"\n"):
                    break
                try:
                    record = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(record, dict):
                    continue
                payload = record.get("payload", {})
                if not isinstance(payload, dict):
                    continue
                if record.get("type") == "session_meta":
                    metadata = payload
                if (
                    record.get("type") == "response_item"
                    and payload.get("type") == "message"
                    and payload.get("role") == "user"
                ):
                    text = text_content(payload)
                    if text and not is_context(text):
                        title = clean_label(text)[:100]
                        break
                if stream.tell() >= 4 * 1024 * 1024:
                    break
        self._cache[path] = identity, metadata, title
        return metadata, title

    def discover(self, cwd: Path | None, include_non_interactive: bool = False) -> list[Session]:
        titles = self._titles()
        wanted = cwd.expanduser().resolve() if cwd else None
        found: dict[str, Session] = {}
        root = self.home / "sessions"
        for path in root.rglob("*.jsonl"):
            try:
                stat = path.stat()
                metadata, fallback = self._metadata(path, (stat.st_dev, stat.st_ino))
                sid = metadata.get("id") or metadata.get("session_id")
                directory = metadata.get("cwd")
                if not isinstance(sid, str) or not isinstance(directory, str):
                    continue
                source = metadata.get("source", "cli")
                kind = source if isinstance(source, str) else "subagent"
                if not include_non_interactive and kind != "cli":
                    continue
                location = Path(directory).expanduser().resolve()
                if wanted is not None and wanted != location:
                    continue
                title, renamed_at = titles.get(sid, (fallback or sid, 0))
                item = Session(
                    sid,
                    path,
                    location,
                    title or fallback or sid,
                    max(stat.st_mtime, renamed_at),
                    kind,
                )
                if sid not in found or item.updated > found[sid].updated:
                    found[sid] = item
            except (OSError, ValueError, RuntimeError):
                continue
        return sorted(found.values(), key=lambda item: (item.updated, item.id), reverse=True)
