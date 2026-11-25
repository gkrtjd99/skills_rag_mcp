"""Usage log and already-loaded exclusion."""

import importlib
import json

import pytest

from skill_rag import index as index_mod
from skill_rag import mcp_server, rerank, usage
from skill_rag import sync as sync_mod


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_RAG_INDEX_PATH", str(tmp_path / "index.lance"))
    monkeypatch.setenv("SKILL_RAG_CORPUS_PATH", str(tmp_path / "skills"))
    monkeypatch.setenv("SKILL_RAG_SCORE_THRESHOLD", "0.0")
    from skill_rag import corpus, retrieve

    for module in (corpus, index_mod, retrieve, rerank, sync_mod, mcp_server):
        importlib.reload(module)
    yield
    index_mod.reset()
    sync_mod.reset_cache()


def _mk(root, name, desc):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\nbody\n", encoding="utf-8")


def _events():
    path = usage.usage_path()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_search_and_load_are_logged_without_request_text(tmp_path):
    _mk(tmp_path / "skills", "tdd", "write failing tests first")
    mcp_server.search_skills("write failing tests for my parser", k=5)
    mcp_server.get_skill("tdd")
    mcp_server.get_skill("missing-skill")
    search, load, miss = _events()
    assert search["event"] == "search" and search["status"] == "ok" and search["provider"] == "gate"
    assert [h["name"] for h in search["hits"]] == ["tdd"]
    assert "query" not in search and "parser" not in json.dumps(search)
    assert load == {**load, "event": "load", "name": "tdd", "found": True, "suggested": True}
    assert miss["found"] is False and miss["suggested"] is False
    assert search["session"] == load["session"]


def test_full_mode_keeps_the_request_and_off_writes_nothing(tmp_path, monkeypatch):
    _mk(tmp_path / "skills", "tdd", "write failing tests first")
    monkeypatch.setattr(usage, "USAGE_LOG", "full")
    mcp_server.search_skills("write failing tests", k=5)
    assert _events()[0]["query"] == "write failing tests"
    usage.usage_path().unlink()
    monkeypatch.setattr(usage, "USAGE_LOG", "off")
    mcp_server.search_skills("write failing tests", k=5)
    mcp_server.get_skill("tdd")
    assert _events() == []
    assert usage.loaded_this_session() == {"tdd"}  # still remembered in memory


def test_loaded_skill_is_not_suggested_again(tmp_path):
    root = tmp_path / "skills"
    _mk(root, "tdd", "write failing tests first")
    _mk(root, "pytest-fixtures", "write tests with pytest fixtures")
    first = mcp_server.search_skills("write tests", k=5)
    assert {h["name"] for h in first["hits"]} == {"tdd", "pytest-fixtures"}
    mcp_server.get_skill("tdd")
    second = mcp_server.search_skills("write tests", k=5)
    assert [h["name"] for h in second["hits"]] == ["pytest-fixtures"]
    mcp_server.get_skill("pytest-fixtures")
    assert mcp_server.search_skills("write tests", k=5)["status"] == "no_match"


def test_exclusion_can_be_turned_off(tmp_path, monkeypatch):
    _mk(tmp_path / "skills", "tdd", "write failing tests first")
    monkeypatch.setattr(usage, "EXCLUDE_LOADED", False)
    mcp_server.search_skills("write tests", k=5)
    mcp_server.get_skill("tdd")
    assert [h["name"] for h in mcp_server.search_skills("write tests", k=5)["hits"]] == ["tdd"]


def test_loaded_skill_never_reaches_the_judge(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    _mk(root, "tdd", "write failing tests first")
    _mk(root, "deploy", "publish the website")
    mcp_server.search_skills("anything", k=5)
    mcp_server.get_skill("tdd")
    seen = []
    monkeypatch.setattr(rerank, "RERANK_PROVIDER", "jev")
    monkeypatch.setattr(
        rerank, "judge", lambda q, cands: seen.append([c["name"] for c in cands]) or [0.95] * len(cands)
    )
    res = mcp_server.search_skills("write tests", k=5)
    assert seen == [["deploy"]]
    assert [h["name"] for h in res["hits"]] == ["deploy"]
    assert _events()[-1]["provider"] == "jev"


def test_fallback_to_the_gate_is_logged_as_the_gate(tmp_path, monkeypatch):
    """Review finding: a judge failure returns local-gate results, so the log
    must not attribute them to the configured judge."""
    _mk(tmp_path / "skills", "tdd", "write failing tests first")
    monkeypatch.setattr(rerank, "RERANK_PROVIDER", "jev")
    monkeypatch.setattr(rerank, "_retry_after", 0.0)

    def boom(query, candidates):
        raise RuntimeError("judge down")

    monkeypatch.setattr(rerank, "judge", boom)
    mcp_server.search_skills("write failing tests", k=5)
    assert _events()[-1]["provider"] == "gate"
    mcp_server.search_skills("write failing tests again", k=5)  # cooldown: still the gate
    assert _events()[-1]["provider"] == "gate"


def test_stats_count_loads_after_suggestion_once_per_session(tmp_path):
    path = tmp_path / "log.jsonl"
    rows = [
        {"session": "a", "event": "search", "hits": [{"name": "tdd", "score": 1}, {"name": "deploy", "score": 0.5}]},
        {"session": "a", "event": "load", "name": "tdd", "found": True},
        {"session": "a", "event": "load", "name": "tdd", "found": True},  # same session, counted once
        {"session": "a", "event": "search", "hits": []},
        {"session": "b", "event": "load", "name": "deploy", "found": True},  # never suggested in b
        {"session": "b", "event": "load", "name": "ghost", "found": False},
        "not json",
    ]
    path.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows), encoding="utf-8")
    report = usage.stats(path)
    assert report["searches"] == 2 and report["searches_with_no_hit"] == 1
    assert report["suggestions"] == 2 and report["loaded_after_suggestion"] == 1
    assert report["loaded_without_suggestion"] == 1
    assert report["skills"]["tdd"] == {"suggested": 1, "loaded_after_suggestion": 1, "loaded_without_suggestion": 0}
    assert report["skills"]["deploy"] == {"suggested": 1, "loaded_after_suggestion": 0, "loaded_without_suggestion": 1}
    assert usage.stats(tmp_path / "absent.jsonl")["searches"] == 0


def test_usage_command(tmp_path):
    from typer.testing import CliRunner

    from skill_rag.cli import app

    _mk(tmp_path / "skills", "tdd", "write failing tests first")
    mcp_server.search_skills("write failing tests", k=5)
    mcp_server.get_skill("tdd")
    result = CliRunner().invoke(app, ["usage"])
    assert result.exit_code == 0
    assert "suggestions     : 1, loaded afterwards: 1 (100%)" in result.stdout
    assert "tdd: suggested 1, loaded after 1" in result.stdout
