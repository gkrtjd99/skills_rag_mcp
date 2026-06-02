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


def test_uninstall_keeps_stray_file_in_non_purge(tmp_path):
    corpus = tmp_path / "skills"
    corpus.mkdir()
    stray = corpus / "notes.txt"
    stray.write_text("hello", encoding="utf-8")

    report = lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[])

    assert stray.exists()                       # non-symlink file preserved
    assert "notes.txt" in report["corpus"]["kept"]


def test_uninstall_leaves_real_dir_harness_link_untouched(tmp_path):
    corpus = tmp_path / "skills"
    corpus.mkdir()
    harness = tmp_path / "claude" / "skills"
    real = harness / "using-skill-rag"          # a real dir, NOT a symlink
    real.mkdir(parents=True)
    (real / "marker").write_text("x", encoding="utf-8")

    report = lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[harness])

    assert real.exists()                        # real dir not removed
    assert report["harness_links_removed"] == []


class _FakeCollect:
    def apply(self, target=None, sources=None, dry_run=False):
        return None


class _FakeSync:
    def run_sync(self):
        return {"added": [], "updated": [], "removed": [], "unchanged": 0}


def test_install_copies_bootstrap_and_links_harness(tmp_path, monkeypatch):
    corpus = tmp_path / "skills"
    harness = tmp_path / "claude" / "skills"
    monkeypatch.setattr(lifecycle, "collect", _FakeCollect(), raising=True)
    monkeypatch.setattr(lifecycle, "sync", _FakeSync(), raising=True)

    report = lifecycle.install(
        repo=tmp_path / "repo", corpus_path=corpus, harness_skill_dirs=[harness]
    )

    assert (corpus / "using-skill-rag" / "SKILL.md").exists()  # bootstrap copied
    assert (harness / "using-skill-rag").is_symlink()          # harness link
    assert report["bootstrap_installed"] is True
    assert report["collect_ran"] is True
    assert report["sync_ran"] is True


def test_install_dry_run_writes_nothing(tmp_path, monkeypatch):
    corpus = tmp_path / "skills"
    harness = tmp_path / "claude" / "skills"
    # dry_run must not call collect/sync; stub them so a stray call would be obvious
    monkeypatch.setattr(lifecycle, "collect", _FakeCollect(), raising=True)
    monkeypatch.setattr(lifecycle, "sync", _FakeSync(), raising=True)

    report = lifecycle.install(
        repo=tmp_path / "repo", corpus_path=corpus, harness_skill_dirs=[harness], dry_run=True
    )

    assert not (corpus / "using-skill-rag").exists()   # nothing copied
    assert not harness.exists() or not (harness / "using-skill-rag").exists()
    assert report["collect_ran"] is False
    assert report["sync_ran"] is False
    assert "claude" in report["mcp"] and "codex" in report["mcp"]  # preview_modes populated


def test_install_is_idempotent_for_bootstrap(tmp_path, monkeypatch):
    corpus = tmp_path / "skills"
    harness = tmp_path / "claude" / "skills"
    monkeypatch.setattr(lifecycle, "collect", _FakeCollect(), raising=True)
    monkeypatch.setattr(lifecycle, "sync", _FakeSync(), raising=True)

    first = lifecycle.install(repo=tmp_path / "repo", corpus_path=corpus, harness_skill_dirs=[harness])
    second = lifecycle.install(repo=tmp_path / "repo", corpus_path=corpus, harness_skill_dirs=[harness])

    assert first["bootstrap_installed"] is True
    assert second["bootstrap_installed"] is False   # already present, not recopied
    assert (corpus / "using-skill-rag" / "SKILL.md").exists()


def test_install_dry_run_previews_mcp(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle.mcp_config, "preview_modes", lambda **k: {"claude": "file", "codex": "file"})
    report = lifecycle.install(
        repo=tmp_path / "repo", corpus_path=tmp_path / "skills",
        harness_skill_dirs=[tmp_path / "h"], dry_run=True,
    )
    assert report["mcp"] == {"claude": "file", "codex": "file"}
