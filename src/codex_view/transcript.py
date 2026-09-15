"""An incremental, read-only decoder for newline-terminated rollout records."""

import json
import os
import uuid
from pathlib import Path

from .render import make_renderer
from .sessions import is_context, text_content


class Transcript:
    def __init__(self, path: Path):
        self.path = path
        self.renderer = make_renderer()
        self.messages: list[dict] = []
        self.generation = uuid.uuid4().hex
        self.available = True
        self.skipped_records = 0
        self._identity = None
        self._stamp = None
        self._offset = 0
        self._pending = b""
        self._anchor = b""

    def _reset(self):
        self.generation = uuid.uuid4().hex
        self.messages = []
        self._offset = 0
        self._pending = b""
        self._anchor = b""
        self.skipped_records = 0

    def _decode(self, line: bytes, offset: int) -> dict | None:
        try:
            record = json.loads(line)
        except (ValueError, UnicodeError):
            self.skipped_records += 1
            return None
        if not isinstance(record, dict) or record.get("type") != "response_item":
            return None
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "message":
            return None
        role = payload.get("role")
        phase = payload.get("phase") or payload.get("channel") or ""
        if role not in ("user", "assistant") or phase not in (
            "",
            "final",
            "final_answer",
            "commentary",
        ):
            return None
        text = text_content(payload)
        if not text.strip() or (role == "user" and is_context(text)):
            return None
        return {
            "id": f"{self.generation}-{offset}",
            "role": role,
            "phase": "progress" if phase == "commentary" else "message",
            "time": record.get("timestamp", ""),
            "html": self.renderer.render(text),
        }

    def poll(self) -> tuple[bool, list[dict]]:
        """Return (reset, appended messages). Incomplete bytes remain buffered."""
        try:
            with self.path.open("rb") as stream:
                stat = os.fstat(stream.fileno())
                identity = stat.st_dev, stat.st_ino
                stamp = identity, stat.st_size, stat.st_mtime_ns
                self.available = True
                if stamp == self._stamp:
                    return False, []
                reset = self._identity is not None and (
                    identity != self._identity or stat.st_size < self._offset
                )
                if not reset and self._anchor:
                    stream.seek(self._offset - len(self._anchor))
                    reset = stream.read(len(self._anchor)) != self._anchor
                if reset:
                    self._reset()
                self._identity = identity
                stream.seek(self._offset)
                added = []
                # Read only the size observed above; a busy writer cannot keep a poll
                # alive indefinitely. Further bytes are picked up on the next poll.
                remaining = stat.st_size - self._offset
                while remaining > 0:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        break
                    start = self._offset - len(self._pending)
                    self._offset += len(chunk)
                    remaining -= len(chunk)
                    lines = (self._pending + chunk).split(b"\n")
                    self._pending = lines.pop()
                    for line in lines:
                        message = self._decode(line, start)
                        if message is not None:
                            self.messages.append(message)
                            added.append(message)
                        start += len(line) + 1
                stream.seek(max(0, self._offset - 128))
                self._anchor = stream.read(min(128, self._offset))
                self._stamp = stamp
                return reset, added
        except OSError:
            self.available = False
            return False, []
