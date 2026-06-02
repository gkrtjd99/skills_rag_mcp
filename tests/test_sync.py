import pytest

from skill_rag import index as index_mod
from skill_rag import sync as sync_mod


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_RAG_INDEX_PATH", str(tmp_path / "index.lance"))
    monkeypatch.setenv("SKILL_RAG_CORPUS_PATH", str(tmp_path / "skills"))
    import importlib
    from skill_rag import corpus
    importlib.reload(corpus)
    importlib.reload(index_mod)
    importlib.reload(sync_mod)
    from skill_rag import translate as translate_mod
    # Stub out translation — sync correctness tests don't depend on translated
    # text, and this keeps them from loading the real MT model.
    monkeypatch.setattr(translate_mod, "translate", lambda text: "")
    yield
    index_mod.reset()


def _mk(corpus_root, name, desc="d", body="b", frontmatter_name=None):
    d = corpus_root / name
    d.mkdir(parents=True, exist_ok=True)
    skill_name = frontmatter_name or name
    (d / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: {desc}\n---\n{body}\n", encoding="utf-8"
    )


def test_sync_adds_skills(tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo")
    _mk(corpus_root, "bar")
    report = sync_mod.run_sync()
    assert sorted(report["added"]) == ["bar", "foo"]
    assert report["updated"] == []
    assert report["removed"] == []
    assert sorted(r["name"] for r in index_mod.list_indexed()) == ["bar", "foo"]


def test_sync_detects_modification(tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo", desc="old")
    sync_mod.run_sync()
    _mk(corpus_root, "foo", desc="new")
    report = sync_mod.run_sync()
    assert report["updated"] == ["foo"]
    rows = index_mod.list_indexed()
    assert rows[0]["description"] == "new"


def test_sync_detects_removal(tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo")
    _mk(corpus_root, "bar")
    sync_mod.run_sync()
    (corpus_root / "foo" / "SKILL.md").unlink()
    (corpus_root / "foo").rmdir()
    report = sync_mod.run_sync()
    assert report["removed"] == ["foo"]
    rows = index_mod.list_indexed()
    assert [r["name"] for r in rows] == ["bar"]


def test_sync_skips_duplicate_frontmatter_names(tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "first", frontmatter_name="same")
    _mk(corpus_root, "second", frontmatter_name="same")

    report = sync_mod.run_sync()

    assert report["added"] == ["same"]
    assert report["duplicate_names"] == [
        {
            "name": "same",
            "kept": str(corpus_root / "first" / "SKILL.md"),
            "skipped": str(corpus_root / "second" / "SKILL.md"),
        }
    ]
    rows = index_mod.list_indexed()
    assert len(rows) == 1
    assert rows[0]["path"] == str(corpus_root / "first" / "SKILL.md")


def test_sync_removes_previously_indexed_duplicate_name(tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "second", frontmatter_name="same")
    sync_mod.run_sync()
    _mk(corpus_root, "first", frontmatter_name="same")
    sync_mod.run_sync()
    rows = index_mod.list_indexed()
    assert len(rows) == 1
    assert rows[0]["path"] == str(corpus_root / "first" / "SKILL.md")


def test_sync_if_stale_skips_within_ttl(monkeypatch, tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo")

    times = [100.0]
    monkeypatch.setattr(sync_mod.time, "monotonic", lambda: times[0])

    sync_mod.sync_if_stale(ttl=30.0)
    assert len(index_mod.list_indexed()) == 1

    _mk(corpus_root, "bar")
    times[0] = 120.0  # within 30s
    sync_mod.sync_if_stale(ttl=30.0)
    assert len(index_mod.list_indexed()) == 1  # not picked up


def test_sync_if_stale_runs_after_ttl(monkeypatch, tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo")

    times = [100.0]
    monkeypatch.setattr(sync_mod.time, "monotonic", lambda: times[0])

    sync_mod.sync_if_stale(ttl=30.0)
    _mk(corpus_root, "bar")
    times[0] = 200.0  # past TTL
    sync_mod.sync_if_stale(ttl=30.0)
    assert sorted(r["name"] for r in index_mod.list_indexed()) == ["bar", "foo"]


def test_sync_if_stale_force_with_ttl_zero(monkeypatch, tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo")
    times = [100.0]
    monkeypatch.setattr(sync_mod.time, "monotonic", lambda: times[0])

    sync_mod.sync_if_stale(ttl=30.0)
    _mk(corpus_root, "bar")
    # No time advance, but ttl=0 forces.
    sync_mod.sync_if_stale(ttl=0)
    assert sorted(r["name"] for r in index_mod.list_indexed()) == ["bar", "foo"]


def test_sync_translates_only_new_and_changed(tmp_path, monkeypatch):
    from skill_rag import translate as translate_mod

    calls = []

    def fake(text):
        calls.append(text)
        return f"T[{text}]"

    monkeypatch.setattr(translate_mod, "translate", fake)
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo", desc="alpha")
    sync_mod.run_sync()
    assert calls == ["alpha"]  # new -> translated

    calls.clear()
    _mk(corpus_root, "foo", desc="beta")   # changed
    _mk(corpus_root, "bar", desc="gamma")  # new
    sync_mod.run_sync()
    assert sorted(calls) == ["beta", "gamma"]  # only changed + new

    calls.clear()
    sync_mod.run_sync()  # nothing changed
    assert calls == []  # unchanged -> not re-translated


def test_sync_translation_lands_in_indexed_text(tmp_path, monkeypatch):
    from skill_rag import translate as translate_mod

    monkeypatch.setattr(translate_mod, "translate", lambda text: "번역결과")
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo", desc="Deploy")
    sync_mod.run_sync()
    row = index_mod.list_indexed()[0]
    assert "번역결과" in row["text"]
