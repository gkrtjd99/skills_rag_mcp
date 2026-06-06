import pytest

from skill_rag import index as index_mod
from skill_rag import retrieve
from skill_rag.models import SkillRecord


@pytest.fixture(autouse=True)
def isolated_index(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_RAG_INDEX_PATH", str(tmp_path / "index.lance"))
    import importlib
    importlib.reload(index_mod)
    importlib.reload(retrieve)
    yield
    index_mod.reset()


def _seed():
    index_mod.upsert([
        SkillRecord(
            name="brainstorming",
            description="explore ideas, requirements, and design before implementation",
            path="/x/brainstorming/SKILL.md",
            body="b",
            content_hash="h1",
        ),
        SkillRecord(
            name="tdd",
            description="write failing tests first then implement",
            path="/x/tdd/SKILL.md",
            body="b",
            content_hash="h2",
        ),
    ])


def test_relevant_query_returns_ok(monkeypatch):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.0)
    _seed()
    res = retrieve.search("explore design ideas")
    assert res["status"] == "ok"
    assert len(res["hits"]) >= 1
    assert all("name" in h and "description" in h and "score" in h for h in res["hits"])


def test_threshold_filters_out_low_scores(monkeypatch):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.99)
    _seed()
    res = retrieve.search("totally unrelated random words asdf qwer")
    assert res["status"] == "no_match"
    assert res["hits"] == []
    assert "message" in res


def test_empty_corpus_returns_no_match():
    res = retrieve.search("anything")
    assert res["status"] == "no_match"
    assert res["hits"] == []


def test_lexical_rescue_when_dense_below_threshold(monkeypatch):
    # Dense can never pass; only the BM25 keyword path can rescue a hit.
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.99)
    monkeypatch.setattr(retrieve, "BM25_THRESHOLD", 0.1)
    index_mod.upsert([
        SkillRecord(
            name="vercel-deploy",
            description="ship apps",
            path="/x/vercel-deploy/SKILL.md",
            body="use this when you deploy a website to vercel and want a preview url",
            content_hash="h1",
        ),
        SkillRecord(
            name="brainstorming",
            description="explore ideas",
            path="/x/brainstorming/SKILL.md",
            body="design the feature first",
            content_hash="h2",
        ),
    ])
    res = retrieve.search("vercel deploy", k=5)
    assert res["status"] == "ok"
    names = [h["name"] for h in res["hits"]]
    assert names[0] == "vercel-deploy"


def test_body_keyword_matches_when_description_does_not(monkeypatch):
    # The keyword lives only in the body, not the one-line description.
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.99)
    monkeypatch.setattr(retrieve, "BM25_THRESHOLD", 0.1)
    index_mod.upsert([
        SkillRecord(
            name="worktrees",
            description="isolate your workspace",
            path="/x/worktrees/SKILL.md",
            body="run git worktree to separate parallel branches cleanly",
            content_hash="h1",
        ),
    ])
    res = retrieve.search("git worktree", k=5)
    assert res["status"] == "ok"
    assert res["hits"][0]["name"] == "worktrees"


def test_no_match_when_neither_signal_passes(monkeypatch):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.99)
    _seed()
    res = retrieve.search("zzz qwerty asdf nonexistent tokens", k=5)
    assert res["status"] == "no_match"
    assert res["hits"] == []


def test_hits_include_agent_field(monkeypatch):
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.0)
    _seed()
    res = retrieve.search("explore design ideas")
    assert res["status"] == "ok"
    assert "agent" in res["hits"][0]


def test_query_is_normalized_before_encoding(monkeypatch):
    # The glued Korean query must reach the encoder spaced at the boundary.
    seen = {}

    def fake_encode_one(text, name=None):
        seen["text"] = text
        import numpy as np
        from skill_rag.embed import model_dim
        return np.zeros(model_dim(), dtype="float32")

    _seed()
    monkeypatch.setattr(retrieve, "encode_one", fake_encode_one)
    retrieve.search("vercel에 배포", k=5)
    assert seen["text"] == "vercel 에 배포"


@pytest.mark.parametrize(
    "query",
    [
        "A", "b", "C", "D",        # multiple-choice answers
        "1", "12",                 # numbered / progress answers (digits-only)
        "네", "넵", "예", "아니요", "좋아요", "수정", "다음", "잘 모르겠어요",
        "yes", "No", "OK", "okay", "next", "idk", "done.",
        "  네 ", "yes!", "다음…",   # whitespace + trailing punctuation
    ],
)
def test_is_conversational_true(query):
    assert retrieve.is_conversational(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "",                              # empty -> stays on no_match path
        "deploy to vercel",
        "no caching strategy works",     # contains "no" but is a real query
        "ok google how do I index",      # contains "ok" but is a real query
        "write a PRD for a chatbot",
        "리액트 성능 최적화",
        "revise the database schema migration",  # contains "revise" but real
        "4/12",                          # progress string, not all-digits -> not bare
    ],
)
def test_is_conversational_false(query):
    assert retrieve.is_conversational(query) is False


def test_skip_response_shape():
    res = retrieve.skip_response()
    assert res["status"] == "skip"
    assert res["hits"] == []
    assert "task or topic" in res["message"]


@pytest.mark.parametrize("query", [None, 123, 4.5, [], {}, object()])
def test_is_conversational_non_string_returns_false(query):
    # Defensive: never raise on a non-str query; fall through to normal handling.
    assert retrieve.is_conversational(query) is False


@pytest.mark.parametrize("query", ["...", "???", "!!!", "…", "。", "   ", "\t\n"])
def test_is_conversational_punctuation_or_blank_is_not_skipped(query):
    # Punctuation/whitespace-only strips to empty -> not a conversational token.
    assert retrieve.is_conversational(query) is False


@pytest.mark.parametrize("query", ["C++", "A)", "(A)", "[1]", "go", "v2", "x86"])
def test_is_conversational_does_not_overreach(query):
    # Two-char tokens, bracketed choices, and real short topics must not skip.
    assert retrieve.is_conversational(query) is False


@pytest.mark.parametrize("query", ["A.", "No.", "Ok!", "YES", "네.", "다음…"])
def test_is_conversational_trims_trailing_punctuation(query):
    assert retrieve.is_conversational(query) is True


def test_search_does_not_skip_conversational_query(monkeypatch):
    # retrieve.search itself never short-circuits (the CLI debug path always
    # searches); only the MCP wrapper skips. A bare letter just finds no match.
    monkeypatch.setattr(retrieve, "SCORE_THRESHOLD", 0.99)
    _seed()
    res = retrieve.search("A", k=5)
    assert res["status"] == "no_match"
