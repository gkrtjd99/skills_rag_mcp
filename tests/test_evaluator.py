import json

import pytest

from skill_rag import index as index_mod
from skill_rag.evaluator import evaluate, load_cases
from skill_rag.models import SkillRecord


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_RAG_INDEX_PATH", str(tmp_path / "index.lance"))
    monkeypatch.setenv("SKILL_RAG_SCORE_THRESHOLD", "0.0")
    import importlib
    from skill_rag import corpus, retrieve
    importlib.reload(corpus)
    importlib.reload(index_mod)
    importlib.reload(retrieve)
    yield
    index_mod.reset()


def test_load_cases(tmp_path):
    p = tmp_path / "q.jsonl"
    p.write_text(
        '{"query": "q1", "expected": "foo"}\n'
        '{"query": "q2", "expected": ["bar", "baz"]}\n'
    )
    cases = load_cases(p)
    assert len(cases) == 2
    assert cases[0].expected == ["foo"]
    assert cases[1].expected == ["bar", "baz"]


def test_evaluate_recall(tmp_path):
    index_mod.upsert([
        SkillRecord(name="foo", description="alpha beta",
                    path="/x/foo/SKILL.md", body="", content_hash="h1"),
        SkillRecord(name="bar", description="gamma delta",
                    path="/x/bar/SKILL.md", body="", content_hash="h2"),
    ])
    p = tmp_path / "q.jsonl"
    p.write_text(
        '{"query": "alpha", "expected": "foo"}\n'
        '{"query": "gamma", "expected": "bar"}\n'
    )
    report = evaluate(load_cases(p), k=5)
    assert report.n == 2
    assert report.recall_at_k == 1.0
    assert report.p95_ms >= 0
