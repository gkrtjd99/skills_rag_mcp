import threading
import time

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
    monkeypatch.setattr(translate_mod, "translate_for_index", lambda text: ("", "skipped"))
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


def test_sync_rebuilds_v6_cache_before_diffing(tmp_path):
    import lancedb
    import pyarrow as pa

    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo", desc="new content")
    db = lancedb.connect(str(index_mod.index_path()))
    old_schema = pa.schema(
        [
            pa.field("path", pa.string()),
            pa.field("name", pa.string()),
            pa.field("description", pa.string()),
            pa.field("content_hash", pa.string()),
            pa.field("text", pa.string()),
            pa.field("agent", pa.string()),
            pa.field("translation_status", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), 32)),
        ]
    )
    db.create_table(index_mod.TABLE_NAME, schema=old_schema)

    report = sync_mod.run_sync()

    assert report["added"] == ["foo"]
    assert index_mod.open_table().schema.metadata[b"skill-rag-schema"] == b"11"


def test_sync_can_use_an_injected_corpus_path(tmp_path):
    alternate = tmp_path / "alternate-skills"
    _mk(alternate, "only-here")

    report = sync_mod.run_sync(corpus_path=alternate)

    assert report["added"] == ["only-here"]
    assert [row["path"] for row in index_mod.list_indexed()] == [
        str(alternate / "only-here" / "SKILL.md")
    ]


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
    monkeypatch.setattr(sync_mod, "_monotonic", lambda: times[0])

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
    monkeypatch.setattr(sync_mod, "_monotonic", lambda: times[0])

    sync_mod.sync_if_stale(ttl=30.0)
    _mk(corpus_root, "bar")
    times[0] = 200.0  # past TTL
    sync_mod.sync_if_stale(ttl=30.0)
    assert sorted(r["name"] for r in index_mod.list_indexed()) == ["bar", "foo"]


def test_sync_if_stale_force_with_ttl_zero(monkeypatch, tmp_path):
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo")
    times = [100.0]
    monkeypatch.setattr(sync_mod, "_monotonic", lambda: times[0])

    sync_mod.sync_if_stale(ttl=30.0)
    _mk(corpus_root, "bar")
    # No time advance, but ttl=0 forces.
    sync_mod.sync_if_stale(ttl=0)
    assert sorted(r["name"] for r in index_mod.list_indexed()) == ["bar", "foo"]


def test_run_sync_serializes_concurrent_calls(monkeypatch):
    active = 0
    max_active = 0
    guard = threading.Lock()

    def fake_run(_corpus_path=None):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.01)
        with guard:
            active -= 1
        return {"added": [], "updated": [], "removed": [], "unchanged": 0,
                "translation_retried": [], "duplicate_names": []}

    monkeypatch.setattr(sync_mod, "_run_sync", fake_run)
    threads = [threading.Thread(target=sync_mod.run_sync) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1


def test_sync_translates_only_new_and_changed(tmp_path, monkeypatch):
    from skill_rag import translate as translate_mod

    calls = []

    def fake(text):
        calls.append(text)
        return f"T[{text}]"

    monkeypatch.setattr(translate_mod, "translate_for_index", lambda text: (fake(text), "ok"))
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

    monkeypatch.setattr(translate_mod, "translate_for_index", lambda text: ("번역결과", "ok"))
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo", desc="Deploy")
    sync_mod.run_sync()
    row = index_mod.list_indexed()[0]
    assert "번역결과" in row["text"]
    assert row["translation_status"] == "ok"


def test_sync_retries_failed_translation_for_unchanged_record(tmp_path, monkeypatch):
    from skill_rag import translate as translate_mod

    outcomes = [("", "failed"), ("번역결과", "ok")]

    def fake(text):
        return outcomes.pop(0)

    monkeypatch.setattr(translate_mod, "translate_for_index", fake)
    monkeypatch.setattr(translate_mod, "TRANSLATE_ENABLED", True)
    corpus_root = tmp_path / "skills"
    _mk(corpus_root, "foo", desc="Deploy")

    first = sync_mod.run_sync()
    first_row = index_mod.list_indexed()[0]
    assert first["added"] == ["foo"]
    assert first_row["translation_status"] == "failed"
    assert "번역결과" not in first_row["text"]

    second = sync_mod.run_sync()
    second_row = index_mod.list_indexed()[0]
    assert second["translation_retried"] == ["foo"]
    assert second["unchanged"] == 0
    assert second_row["translation_status"] == "ok"
    assert "번역결과" in second_row["text"]
