import json
import os

from conftest import append, record

from codex_view.sessions import SessionCatalog


def test_current_directory_all_and_source_filter(corpus):
    home, project, other, create = corpus
    create("local")
    create("elsewhere", cwd=other)
    create("child", source={"subagent": {"thread_spawn": {}}})
    create("exec", source="exec")
    catalog = SessionCatalog(home)
    assert [s.id for s in catalog.discover(project)] == ["local"]
    assert {s.id for s in catalog.discover(None)} == {"local", "elsewhere"}
    assert {s.id for s in catalog.discover(project, True)} == {"local", "child", "exec"}


def test_titles_renames_and_incomplete_index(corpus):
    home, project, _, create = corpus
    create()
    index = home / "session_index.jsonl"
    index.write_text("broken\n[]\n", encoding="utf-8")
    append(
        index,
        {"id": "session-one", "thread_name": "New name", "updated_at": "2026-01-02T00:00:00Z"},
    )
    append(
        index,
        {"id": "session-one", "thread_name": "Old name", "updated_at": "2026-01-01T00:00:00Z"},
    )
    with index.open("a") as stream:
        stream.write('{"id":')
    assert SessionCatalog(home).discover(project)[0].title == "New name"


def test_fallback_new_sessions_and_symlink_directory(corpus, tmp_path):
    home, project, _, create = corpus
    first = create(prompt="A useful question")
    os.utime(first, (10, 10))
    catalog = SessionCatalog(home)
    assert catalog.discover(project)[0].title == "A useful question"
    second = create("session-two", prompt="New conversation")
    os.utime(second, (20, 20))
    assert catalog.discover(project)[0].id == "session-two"
    alias = tmp_path / "alias"
    alias.symlink_to(project, target_is_directory=True)
    assert len(catalog.discover(alias)) == 2


def test_missing_malformed_and_partial_metadata(corpus):
    home, project, _, create = corpus
    path = create()
    path.write_bytes(b'{"type": "session_meta",')
    assert SessionCatalog(home).discover(project) == []
    path.write_text(json.dumps({"type": "session_meta", "payload": []}) + "\n")
    assert SessionCatalog(home).discover(project) == []
    assert SessionCatalog(home / "missing").discover(None) == []


def test_session_without_first_prompt_is_rediscovered(corpus):
    home, project, _, create = corpus
    path = create(prompt="")
    catalog = SessionCatalog(home)
    assert catalog.discover(project)[0].title == "session-one"
    append(path, record("First real question", "user", ""))
    assert catalog.discover(project)[0].title == "First real question"
