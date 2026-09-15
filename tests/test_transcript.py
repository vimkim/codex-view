import json

from conftest import append, record

from codex_view.render import make_renderer
from codex_view.transcript import Transcript


def test_partial_unicode_record_waits_and_does_not_duplicate(tmp_path):
    path = tmp_path / "session.jsonl"
    raw = json.dumps(record("안녕, world"), ensure_ascii=False).encode() + b"\n"
    split = raw.index("안".encode()) + 1
    path.write_bytes(raw[:split])
    reader = Transcript(path)
    assert reader.poll() == (False, [])
    with path.open("ab") as stream:
        stream.write(raw[split:-1])
    assert reader.poll() == (False, [])
    with path.open("ab") as stream:
        stream.write(b"\n")
    reset, messages = reader.poll()
    assert not reset and len(messages) == 1
    assert "안녕" in messages[0]["html"]
    assert reader.poll() == (False, [])
    assert len(reader.messages) == 1


def test_append_ids_stay_stable_and_repeated_text_is_not_dropped(tmp_path):
    path = tmp_path / "session.jsonl"
    append(path, record("repeat"))
    reader = Transcript(path)
    reader.poll()
    original = reader.messages[0]["id"]
    append(path, record("repeat"))
    _, added = reader.poll()
    assert len(added) == 1
    assert added[0]["id"] != original
    assert reader.messages[0]["id"] == original


def test_truncate_regrow_and_replace_reset_generation(tmp_path):
    path = tmp_path / "session.jsonl"
    append(path, record("Original"))
    reader = Transcript(path)
    reader.poll()
    generation = reader.generation
    # Rewrite beyond the original length: size alone cannot detect this reset.
    path.write_text(json.dumps(record("Replacement " * 100)) + "\n")
    reset, added = reader.poll()
    assert reset and len(added) == 1 and reader.generation != generation
    assert len(reader.messages) == 1
    replacement = tmp_path / "replacement"
    append(replacement, record("A new inode"))
    replacement.replace(path)
    assert reader.poll()[0] is True
    path.write_bytes(b"")
    assert reader.poll()[0] is True
    assert reader.messages == []


def test_unavailable_file_preserves_messages_and_recovers(tmp_path):
    path = tmp_path / "session.jsonl"
    append(path, record("Keep me"))
    reader = Transcript(path)
    reader.poll()
    moved = path.with_suffix(".moved")
    path.rename(moved)
    reader.poll()
    assert not reader.available and len(reader.messages) == 1
    moved.rename(path)
    reader.poll()
    assert reader.available and len(reader.messages) == 1


def test_context_tools_reasoning_and_malformed_records_are_not_messages(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_bytes(b'invalid json\n[]\n{"type":"response_item","payload":[]}\n')
    append(path, record("secret", "assistant", "analysis"))
    append(path, record("secret", "developer", ""))
    append(path, record("# AGENTS.md instructions for /tmp\nsecret", "user", ""))
    append(
        path, {"type": "response_item", "payload": {"type": "function_call", "arguments": "secret"}}
    )
    append(path, record("Visible progress", phase="commentary"))
    append(path, record("Visible answer"))
    reader = Transcript(path)
    reader.poll()
    assert len(reader.messages) == 2
    assert reader.messages[0]["phase"] == "progress"
    assert reader.skipped_records == 1
    assert "secret" not in json.dumps(reader.messages)


def test_math_code_tables_and_html_escaping():
    rendered = make_renderer().render(r"""
Inline \(\frac{a_1}{\sqrt{n}}\) and $x^2$.

\[
\mathbb{E}[X^2] = \frac{\sigma^2}{n}
\]

| A | B |
|---|---|
| 1 | 2 |

`\(literal code\)`

```python
print("$not_math$")
```

<script>alert("bad")</script>
[bad](javascript:alert(1))
""")
    assert r"\(\frac{a_1}{\sqrt{n}}\)" in rendered
    assert r"\mathbb{E}[X^2]" in rendered
    assert "<table>" in rendered
    assert "<code>\\(literal code\\)</code>" in rendered
    assert "<script>" not in rendered
    assert 'href="javascript:' not in rendered
    assert "$not_math$" in rendered
