from pathlib import Path

from skill_rag import corpus


def test_default_corpus_path(monkeypatch):
    monkeypatch.delenv("SKILL_RAG_CORPUS_PATH", raising=False)
    # Re-import to pick up env change
    import importlib
    importlib.reload(corpus)
    assert corpus.CORPUS_PATH == Path("~/.skills").expanduser()


def test_corpus_path_override(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILL_RAG_CORPUS_PATH", str(tmp_path))
    import importlib
    importlib.reload(corpus)
    assert corpus.CORPUS_PATH == tmp_path


def test_constants_exposed():
    assert corpus.BOOTSTRAP_SKILL_NAME == "using-skill-rag"
    assert 0 < corpus.SCORE_THRESHOLD < 1
    assert corpus.SYNC_TTL_SECONDS > 0
