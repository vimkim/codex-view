"""Exercise the actual terminal UI, rather than mocking selection."""

import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX terminal test")


def read_until(master, needle, timeout=10):
    output = b""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if select.select([master], [], [], 0.1)[0]:
            try:
                output += os.read(master, 65536)
            except OSError:
                break
            if needle in output:
                return output
    raise AssertionError(f"Terminal did not produce {needle!r}: {output[-1000:]!r}")


def test_picker_search_discovers_new_session_and_selects(corpus):
    home, project, _, create = corpus
    create("old", prompt="An earlier conversation")
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 120, 0, 0))
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "codex_view", "--codex-home", str(home), "--port", "0"],
        cwd=project,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={**os.environ, "TERM": "xterm-256color", "PROMPT_TOOLKIT_NO_CPR": "1"},
    )
    os.close(slave)
    try:
        read_until(master, b"Search:")
        create("new", prompt="Brand new conversation")
        os.write(master, b"Brand new")
        read_until(master, b"Brand new conversation")
        os.write(master, b"\r")
        output = read_until(master, b"Ctrl+C")
        assert b"Session: new" in output
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
