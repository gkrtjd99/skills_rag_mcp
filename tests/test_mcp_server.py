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


def test_search_skills_blank_query_stays_no_match(tmp_path):
    # Whitespace-only must keep the existing no_match contract, not become skip.
    res = mcp_server.search_skills("   ", k=5)
    assert res["status"] == "no_match"


def test_search_skills_skip_message_is_actionable(tmp_path):
    res = mcp_server.search_skills("네", k=5)
    assert res["status"] == "skip"
    assert "Do not search again" in res["message"]


@pytest.mark.parametrize("k", [0, -1, 51, True, False])
def test_search_skills_rejects_invalid_k_before_sync(monkeypatch, k):
    monkeypatch.setattr(
        mcp_server.sync_mod,
        "sync_if_stale",
        lambda *a, **k: pytest.fail("invalid k must not sync"),
    )

    with pytest.raises(ValueError, match="k must be an integer"):
        mcp_server.search_skills("A", k=k)


def test_interactive_flow_searches_once_then_skips(tmp_path):
    """Simulate a PRD-coach flow: the opening task searches, the per-turn
    multiple-choice/ack replies all skip without touching the index."""
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "brainstorming", desc="explore product ideas and requirements before building")

    opening = mcp_server.search_skills(
        "act as a PRD coach and interview me to draft a product spec", k=5
    )
    assert opening["status"] in {"ok", "no_match"}  # a real retrieval ran

    for reply in ["A", "B", "네", "잘 모르겠어요", "다음", "1", "done"]:
        res = mcp_server.search_skills(reply, k=5)
        assert res["status"] == "skip", f"{reply!r} should skip"
        assert res["hits"] == []
