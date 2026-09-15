# codex-view

Select a saved Codex CLI conversation in your terminal and read it live in your
browser, with rendered Markdown and LaTeX equations.

```bash
cd /path/to/your/project
codex-view
```

Use the searchable session picker, press Enter, then open
one of the printed LAN/VPN URLs in your browser. Continue chatting in Codex CLI;
new saved messages appear automatically. Ctrl+C stops the viewer.

## Install with uv

Requires [uv](https://docs.astral.sh/uv/). The development interpreter is pinned
to Python **3.14.6** in `.python-version`. The package supports Python 3.12+.

```bash
git clone https://github.com/vimkim/codex-view.git
cd codex-view
uv sync --locked
uv tool install --python 3.14.6 .
codex-view --help
```

`uv tool install` installs the command in uv's user executable directory. If that
directory is not on PATH, run `uv tool update-shell` and open a new shell.

For development, run without installing the command globally:

```bash
uv run codex-view -C /path/to/your/project
```

After changing the source, update the installed copy:

```bash
uv tool install --reinstall --python 3.14.6 .
```

## Select a conversation

By default, the picker shows interactive CLI sessions whose recorded working
directory matches the directory where you launched the command. Paths are
resolved, so a symlink to the same directory also matches. This is an exact
directory match, not a recursive search of child projects.

```bash
# Current directory, with an interactive picker
codex-view

# Sessions across all directories
codex-view --all

# Most recently updated matching session, without a picker
codex-view --last

# A different directory
codex-view -C ~/projects/example

# A specific session ID or a unique ID prefix; bypasses the directory filter
codex-view 01234567-89ab-cdef-0123-456789abcdef

# List sessions for scripting, without starting a server
codex-view --list --json

# Include non-interactive and subagent sessions
codex-view --all --include-non-interactive

# A custom Codex data directory; CODEX_HOME is also respected
codex-view --codex-home /path/to/.codex --all
```

In the picker, type to search titles, IDs and directories. Use the up/down keys
to select, Enter to start the viewer, or Escape/Ctrl+C to cancel. The list
refreshes every two seconds, including newly created sessions. Each viewer
instance serves the session selected at launch; restart the command to select
another, or run a second instance on another port.

The default data directory is `$CODEX_HOME`, or `~/.codex` when unset. Active
session storage under `sessions/` is searched; `archived_sessions/` is not.
Titles come from `session_index.jsonl`, with the first user message as a fallback.

## LAN, VPN and SSH access

By default, the server binds to all IPv4 interfaces for LAN/VPN access:

```bash
codex-view --port 8765
```

Open `http://SERVER_VPN_IP:8765`. The viewer permits direct IP and hostname
access. `0.0.0.0` is the bind address, not the address to enter in your browser.
It has no application login; access is controlled by your network/VPN.

Startup lists the concrete interface URLs for the listener, for example:

```text
Listening: 0.0.0.0:8765
Available addresses:
  http://127.0.0.1:8765
  http://192.168.1.10:8765
  http://10.0.0.2:8765
```

On Linux, discovery uses `ip -j address show up`, including LAN, VPN and bridge
interfaces. Only addresses supported by the listener are shown. With a specific
bind address, only that address is listed. On hosts without `ip`, discovery
falls back to loopback and hostname-resolved addresses. Which address a client
can reach depends on its network routes. IPv6 URLs include brackets and, where
needed, an interface scope.

For local-only access or an SSH tunnel, explicitly select the loopback listener:

```bash
# On the server
codex-view --last --host 127.0.0.1 --port 8765

# In another terminal on your own computer
ssh -N -L 8765:127.0.0.1:8765 USER@SERVER
```

Then open `http://localhost:8765` on your own computer. Keep the tunnel running.
IPv6 bind addresses are also accepted, for example `--host ::1`.

If the port is already occupied, choose another with `--port 8766`, or use
`--port 0` to have the operating system choose an available port.

## Live updates and rendering

- The selected transcript is checked every second; only new bytes are read.
- Incomplete final JSON records are buffered until their terminating newline.
- Server-Sent Events deliver updates to all connected browser tabs.
- Reconnection starts with a fresh snapshot and does not duplicate messages.
- File replacement, truncation, and temporary disappearance are handled.
- Scrolling stays in place unless **Follow new messages** is enabled.
- **Show progress updates** reveals assistant commentary; it is hidden initially.
- Markdown tables, fenced code, `\(...\)`, `\[...\]`, `$...$` and `$$...$$` math
  are supported. MathJax is bundled; no CDN is required at runtime.

Updates appear when Codex writes complete message records. The viewer cannot
display tokens that Codex has not saved yet. It does not send messages, resume
an agent, execute tools, or call an AI API. It shows user/assistant text, not
tool calls, developer instructions or reasoning records. Session logs are never
modified. Images and tool-output attachments are not displayed in this version.

## Run in the background

Use an explicit ID or `--last` when no interactive terminal is available:

```bash
nohup codex-view --last -C /path/to/project --host 0.0.0.0 --port 8765 \
  >codex-view.log 2>&1 &
viewer_pid=$!

# Stop it later in the same shell
kill "$viewer_pid"
```

The tool does not install or change systemd services. SIGINT and SIGTERM stop
the foreground server and its file-following thread.

## Development and verification

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv build
```

Browser integration tests are opt-in:

```bash
uv sync --locked --group browser
uv run --group browser playwright install chromium
CODEX_VIEW_BROWSER_TESTS=1 uv run --group browser pytest -q
```

Tests use synthetic transcripts, never personal session history. They cover
directory/source filtering, session titles, CLI selection, a real POSIX terminal
picker, partial UTF-8 writes, repeated messages, replacement/truncation, safe
Markdown, HTTP serving, SSE recovery and browser math rendering. The terminal
picker integration test requires POSIX; the primary target is Linux.

`uv.lock` records exact development dependencies. `uv tool install .` resolves
the runtime version ranges declared in `pyproject.toml`. To install precisely
the runtime versions in the lockfile:

```bash
uv export --locked --no-dev --no-emit-project --no-hashes \
  --output-file /tmp/codex-view-constraints.txt
uv tool install --python 3.14.6 \
  --constraints /tmp/codex-view-constraints.txt .
```

## Structure

```text
src/codex_view/
  sessions.py       Session discovery, titles and directory filtering
  picker.py         Searchable terminal selection
  transcript.py     Incremental rollout decoding and reset detection
  render.py         Markdown and math handling
  server.py         HTTP server and live event stream
  cli.py            Arguments, lifecycle and installed entry point
  static/           Browser UI and bundled MathJax
tests/              Synthetic fixtures and integration tests
```

The decoder targets Codex JSONL `session_meta` and `response_item` message
records. It accepts the observed `phase`/`channel` variants and skips unknown
record types. A future Codex storage-format change may require a decoder update;
those details are isolated in `sessions.py` and `transcript.py`.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for vendored asset licensing.
