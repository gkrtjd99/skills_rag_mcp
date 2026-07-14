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


def test_uninstall_preserves_untracked_entries(tmp_path):
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

    assert (corpus / "linked").exists()                 # user symlink preserved
    assert (corpus / "using-skill-rag").exists()        # untracked bootstrap preserved
    assert (corpus / "manual").exists()                 # real dir kept
    assert (harness / "using-skill-rag").exists()       # foreign harness link preserved
    assert report["corpus"]["removed_links"] == []


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
    class _Report:
        linked: list[str] = []

    def plan(self, target=None, sources=None):
        return [], self._Report()

    def apply(self, target=None, sources=None, dry_run=False):
        return None


class _FakeSync:
    def run_sync(self, corpus_path=None):
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
    assert report["bootstrap_refreshed"] is False
    assert report["collect_ran"] is True
    assert report["sync_ran"] is True
    state = lifecycle._load_state(corpus)
    assert state["harness_links"][str(harness / "using-skill-rag")] == str(
        (corpus / "using-skill-rag").resolve()
    )


def test_install_syncs_the_same_injected_corpus(tmp_path, monkeypatch):
    corpus = tmp_path / "skills"
    captured = {}

    class SpySync:
        def run_sync(self, corpus_path=None):
            captured["corpus_path"] = corpus_path
            return {"added": [], "updated": [], "removed": [], "unchanged": 0}

    monkeypatch.setattr(lifecycle, "collect", _FakeCollect(), raising=True)
    monkeypatch.setattr(lifecycle, "sync", SpySync(), raising=True)

    lifecycle.install(repo=tmp_path / "repo", corpus_path=corpus, harness_skill_dirs=[])

    assert captured["corpus_path"] == corpus


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


def test_install_preserves_existing_bootstrap_without_refresh(tmp_path, monkeypatch):
    corpus = tmp_path / "skills"
    existing = corpus / "using-skill-rag"
    existing.mkdir(parents=True)
    marker = existing / "SKILL.md"
    marker.write_text("custom bootstrap", encoding="utf-8")
    monkeypatch.setattr(lifecycle, "collect", _FakeCollect(), raising=True)
    monkeypatch.setattr(lifecycle, "sync", _FakeSync(), raising=True)

    report = lifecycle.install(
        repo=tmp_path / "repo", corpus_path=corpus, harness_skill_dirs=[]
    )

    assert marker.read_text(encoding="utf-8") == "custom bootstrap"
    assert report["bootstrap_installed"] is False
    assert report["bootstrap_refreshed"] is False


def test_install_refresh_bootstrap_overwrites_existing(tmp_path, monkeypatch):
    corpus = tmp_path / "skills"
    existing = corpus / "using-skill-rag"
    existing.mkdir(parents=True)
    marker = existing / "SKILL.md"
    marker.write_text("custom bootstrap", encoding="utf-8")
    monkeypatch.setattr(lifecycle, "collect", _FakeCollect(), raising=True)
    monkeypatch.setattr(lifecycle, "sync", _FakeSync(), raising=True)

    report = lifecycle.install(
        repo=tmp_path / "repo",
        corpus_path=corpus,
        harness_skill_dirs=[],
        refresh_bootstrap=True,
    )

    assert "Skill RAG" in marker.read_text(encoding="utf-8")
    assert report["bootstrap_installed"] is False
    assert report["bootstrap_refreshed"] is True


def test_install_refresh_bootstrap_dry_run_preserves_existing(tmp_path, monkeypatch):
    corpus = tmp_path / "skills"
    existing = corpus / "using-skill-rag"
    existing.mkdir(parents=True)
    marker = existing / "SKILL.md"
    marker.write_text("custom bootstrap", encoding="utf-8")
    monkeypatch.setattr(lifecycle, "collect", _FakeCollect(), raising=True)
    monkeypatch.setattr(lifecycle, "sync", _FakeSync(), raising=True)

    report = lifecycle.install(
        repo=tmp_path / "repo",
        corpus_path=corpus,
        harness_skill_dirs=[],
        refresh_bootstrap=True,
        dry_run=True,
    )

    assert marker.read_text(encoding="utf-8") == "custom bootstrap"
    assert report["bootstrap_refreshed"] is True


def test_install_dry_run_previews_mcp(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle.mcp_config, "preview_modes", lambda **k: {"claude": "file", "codex": "file"})
    report = lifecycle.install(
        repo=tmp_path / "repo", corpus_path=tmp_path / "skills",
        harness_skill_dirs=[tmp_path / "h"], dry_run=True,
    )
    assert report["mcp"] == {"claude": "file", "codex": "file"}
