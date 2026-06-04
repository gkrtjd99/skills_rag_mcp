import pytest

from skill_rag import index as index_mod
from skill_rag import mcp_server
from skill_rag import sync as sync_mod


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_RAG_INDEX_PATH", str(tmp_path / "index.lance"))
    monkeypatch.setenv("SKILL_RAG_CORPUS_PATH", str(tmp_path / "skills"))
    monkeypatch.setenv("SKILL_RAG_SCORE_THRESHOLD", "0.0")
    import importlib
    from skill_rag import corpus, retrieve
    importlib.reload(corpus)
    importlib.reload(index_mod)
    importlib.reload(retrieve)
    importlib.reload(sync_mod)
    importlib.reload(mcp_server)
    yield
    index_mod.reset()
    sync_mod.reset_cache()


def _mk(corpus_root, name, desc="d", body="b"):
    d = corpus_root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n{body}\n", encoding="utf-8"
    )


def test_search_skills_returns_ok_for_match(tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "brainstorming", desc="explore ideas before implementation")
    res = mcp_server.search_skills("explore ideas", k=5)
    assert res["status"] == "ok"
    assert any(h["name"] == "brainstorming" for h in res["hits"])


def test_search_skills_returns_no_match_when_empty(tmp_path):
    res = mcp_server.search_skills("anything", k=5)
    assert res["status"] == "no_match"
    assert res["hits"] == []


def test_get_skill_returns_body(tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo", body="hello body")
    mcp_server.search_skills("foo", k=1)  # populate index
    res = mcp_server.get_skill("foo")
    assert res["status"] == "ok"
    assert "hello body" in res["body"]


def test_get_skill_not_found_after_force_sync(tmp_path):
    res = mcp_server.get_skill("does-not-exist")
    assert res["status"] == "not_found"
    assert "again" in res["message"].lower()


def test_get_skill_recovers_via_force_sync(tmp_path, monkeypatch):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo", body="hi")
    # Do NOT call search first — get_skill must trigger sync itself.
    res = mcp_server.get_skill("foo")
    assert res["status"] == "ok"
    assert "hi" in res["body"]


def test_get_skill_works_when_dir_name_differs_from_skill_name(tmp_path):
    """Vercel-style: dir is `react-best-practices/` but frontmatter name is `vercel-react-best-practices`."""
    corpus_root = tmp_path / "skills"
    d = corpus_root / "react-best-practices"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: vercel-react-best-practices\ndescription: react perf\n---\nhello\n",
        encoding="utf-8",
    )
    res = mcp_server.get_skill("vercel-react-best-practices")
    assert res["status"] == "ok"
    assert "hello" in res["body"]


def test_search_skills_skips_conversational_reply(tmp_path, monkeypatch):
    """A bare interactive-flow reply returns skip without syncing or searching."""
    called = {"sync": False, "search": False}
    monkeypatch.setattr(
        mcp_server.sync_mod, "sync_if_stale", lambda *a, **k: called.__setitem__("sync", True)
    )
    monkeypatch.setattr(
        mcp_server.retrieve, "search",
        lambda *a, **k: called.__setitem__("search", True) or {"status": "ok", "hits": []},
    )
    res = mcp_server.search_skills("A", k=5)
    assert res["status"] == "skip"
    assert res["hits"] == []
    assert called == {"sync": False, "search": False}


def test_search_skills_does_not_skip_real_query(tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "brainstorming", desc="explore ideas before implementation")
    res = mcp_server.search_skills("explore ideas before building", k=5)
    assert res["status"] in {"ok", "no_match"}
    assert res["status"] != "skip"
