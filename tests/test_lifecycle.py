from pathlib import Path

import pytest

from skill_rag import lifecycle


@pytest.fixture(autouse=True)
def no_mcp(monkeypatch):
    """Stub MCP edits — exercised separately in test_mcp_config."""
    monkeypatch.setattr(lifecycle.mcp_config, "unregister_claude", lambda **k: "noop")
    monkeypatch.setattr(lifecycle.mcp_config, "unregister_codex", lambda **k: False)
    monkeypatch.setattr(lifecycle.mcp_config, "register_claude", lambda *a, **k: "noop")
    monkeypatch.setattr(lifecycle.mcp_config, "register_codex", lambda *a, **k: False)


def _real_skill(root: Path, name: str) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\n---\nx\n")
    return d


def test_uninstall_removes_symlinks_keeps_real_dirs(tmp_path):
    corpus = tmp_path / "skills"
    corpus.mkdir()
    src = _real_skill(tmp_path / "src", "linked")
    (corpus / "linked").symlink_to(src, target_is_directory=True)
    _real_skill(corpus, "manual")          # hand-placed
    _real_skill(corpus, "using-skill-rag")  # bootstrap
    harness = tmp_path / "claude" / "skills"
    harness.mkdir(parents=True)
    (harness / "using-skill-rag").symlink_to(corpus / "using-skill-rag", target_is_directory=True)

    report = lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[harness])

    assert not (corpus / "linked").exists()             # symlink removed
    assert not (corpus / "using-skill-rag").exists()    # bootstrap removed
    assert (corpus / "manual").exists()                 # real dir kept
    assert not (harness / "using-skill-rag").exists()   # harness link removed
    assert report["corpus"]["removed_links"] == ["linked"]


def test_uninstall_purge_empties_corpus(tmp_path):
    corpus = tmp_path / "skills"
    _real_skill(corpus, "manual")
    _real_skill(corpus, "using-skill-rag")

    lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[], purge=True)

    assert list(corpus.iterdir()) == []


def test_uninstall_dry_run_changes_nothing(tmp_path):
    corpus = tmp_path / "skills"
    corpus.mkdir()
    src = _real_skill(tmp_path / "src", "linked")
    (corpus / "linked").symlink_to(src, target_is_directory=True)

    lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[], dry_run=True)

    assert (corpus / "linked").exists()


def test_uninstall_idempotent_on_empty(tmp_path):
    corpus = tmp_path / "skills"
    corpus.mkdir()
    lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[])  # no error
