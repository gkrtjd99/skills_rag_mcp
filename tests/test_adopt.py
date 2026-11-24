"""adopt / restore: the store becomes the only home of a skill, reversibly."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skill_rag import lifecycle
from skill_rag.cli import app


@pytest.fixture(autouse=True)
def no_mcp(monkeypatch):
    monkeypatch.setattr(lifecycle.mcp_config, "unregister_claude", lambda **k: "noop")
    monkeypatch.setattr(lifecycle.mcp_config, "unregister_codex", lambda **k: False)


def _skill(root: Path, name: str, extra: str | None = None) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\n---\nx\n", encoding="utf-8")
    if extra:
        (d / "scripts").mkdir()
        (d / "scripts" / extra).write_text("print('hi')\n", encoding="utf-8")
    return d


@pytest.fixture
def layout(tmp_path):
    corpus = tmp_path / "skills"
    harness = tmp_path / "claude" / "skills"
    harness.mkdir(parents=True)
    return corpus, harness


def _adopt(corpus, sources, **kwargs):
    return lifecycle.adopt(corpus_path=corpus, sources=sources, sync_index=False, **kwargs)


def _restore(corpus, **kwargs):
    return lifecycle.restore(corpus_path=corpus, sync_index=False, **kwargs)


def test_adopt_moves_skill_with_its_files_and_records_origin(layout):
    corpus, harness = layout
    origin = _skill(harness, "deploy", extra="run.py")

    report = _adopt(corpus, [harness])

    assert [a["name"] for a in report["adopted"]] == ["deploy"]
    assert not origin.exists()  # the harness no longer sees it
    assert (corpus / "deploy" / "SKILL.md").is_file()
    assert (corpus / "deploy" / "scripts" / "run.py").is_file()
    assert not (corpus / "deploy").is_symlink()
    assert lifecycle.adopted_names(corpus) == ["deploy"]
    state = json.loads((corpus / lifecycle.STATE_FILE).read_text())
    assert state["adopted"]["deploy"] == {"origin": str(origin), "store": str(corpus / "deploy")}


def test_restore_puts_it_back_exactly(layout):
    corpus, harness = layout
    origin = _skill(harness, "deploy", extra="run.py")
    _adopt(corpus, [harness])

    report = _restore(corpus)

    assert [r["name"] for r in report["restored"]] == ["deploy"]
    assert (origin / "scripts" / "run.py").is_file()
    assert not (corpus / "deploy").exists()
    assert lifecycle.adopted_names(corpus) == []


def test_dry_run_moves_nothing(layout):
    corpus, harness = layout
    origin = _skill(harness, "deploy")
    report = _adopt(corpus, [harness], dry_run=True)
    assert [a["name"] for a in report["adopted"]] == ["deploy"]
    assert origin.exists() and not corpus.exists()

    _adopt(corpus, [harness])
    report = _restore(corpus, dry_run=True)
    assert [r["name"] for r in report["restored"]] == ["deploy"]
    assert (corpus / "deploy").exists() and not origin.exists()


def test_adopt_only_named_skills(layout):
    corpus, harness = layout
    _skill(harness, "deploy")
    _skill(harness, "tdd")
    report = _adopt(corpus, [harness], names=["tdd"])
    assert [a["name"] for a in report["adopted"]] == ["tdd"]
    assert (harness / "deploy").exists() and not (harness / "tdd").exists()


def test_adopt_skips_bootstrap_symlinks_non_skills_and_nested(layout, tmp_path):
    corpus, harness = layout
    _skill(corpus, "using-skill-rag")
    (harness / "using-skill-rag").symlink_to(corpus / "using-skill-rag", target_is_directory=True)
    elsewhere = _skill(tmp_path / "plugin" / "skills", "managed")
    (harness / "managed").symlink_to(elsewhere, target_is_directory=True)
    (harness / "notes").mkdir()  # no SKILL.md
    _skill(harness / "synced" / "abc", "nested")  # not a direct child

    report = _adopt(corpus, [harness])

    assert report["adopted"] == []
    assert [(s["name"], s["reason"]) for s in report["skipped"]] == [
        ("managed", "is a symlink; managed elsewhere")
    ]
    assert elsewhere.exists() and (harness / "managed").is_symlink()
    assert (harness / "synced" / "abc" / "nested").exists()


def test_adopt_never_overwrites_an_existing_store_entry(layout):
    corpus, harness = layout
    _skill(corpus, "deploy")
    (corpus / "deploy" / "mine.txt").write_text("keep", encoding="utf-8")
    origin = _skill(harness, "deploy")

    report = _adopt(corpus, [harness])

    assert report["adopted"] == []
    assert report["skipped"][0]["name"] == "deploy"
    assert origin.exists() and (corpus / "deploy" / "mine.txt").read_text() == "keep"


def test_adopt_replaces_the_link_collect_made_to_the_same_skill(layout):
    corpus, harness = layout
    origin = _skill(harness, "deploy")
    corpus.mkdir()
    (corpus / "deploy").symlink_to(origin, target_is_directory=True)
    state = lifecycle._empty_state()
    state["collected_links"][str(corpus / "deploy")] = str(origin.resolve())
    lifecycle._write_state(corpus, state)

    _adopt(corpus, [harness])

    assert (corpus / "deploy").is_dir() and not (corpus / "deploy").is_symlink()
    assert not origin.exists()
    assert lifecycle._load_state(corpus)["collected_links"] == {}


def test_first_source_wins_on_duplicate_names(layout, tmp_path):
    corpus, harness = layout
    project = tmp_path / "proj" / ".claude" / "skills"
    _skill(harness, "deploy")
    second = _skill(project, "deploy")
    report = _adopt(corpus, [harness, project])
    assert len(report["adopted"]) == 1 and report["adopted"][0]["origin"] == str(harness / "deploy")
    assert second.exists()
    assert report["skipped"][0]["source"] == str(second)


def test_restore_does_not_overwrite_a_reoccupied_origin(layout):
    corpus, harness = layout
    origin = _skill(harness, "deploy")
    _adopt(corpus, [harness])
    _skill(harness, "deploy")  # reinstalled natively in the meantime
    (origin / "new.txt").write_text("new", encoding="utf-8")

    report = _restore(corpus)

    assert report["restored"] == []
    assert report["conflicts"][0]["reason"] == "original location is occupied"
    assert (corpus / "deploy").exists() and (origin / "new.txt").exists()
    assert lifecycle.adopted_names(corpus) == ["deploy"]


def test_restore_forgets_a_skill_that_is_already_back(layout):
    corpus, harness = layout
    origin = _skill(harness, "deploy")
    _adopt(corpus, [harness])
    (corpus / "deploy").rename(origin)  # moved back by hand

    report = _restore(corpus)

    assert [r["name"] for r in report["restored"]] == ["deploy"]
    assert origin.exists() and lifecycle.adopted_names(corpus) == []


def test_uninstall_restores_adopted_skills_even_with_purge(layout):
    corpus, harness = layout
    origin = _skill(harness, "deploy", extra="run.py")
    _adopt(corpus, [harness])

    report = lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[], purge=True)

    assert report["adopted_restored"] == ["deploy"]
    assert (origin / "scripts" / "run.py").is_file()
    assert list(corpus.iterdir()) == []


def test_uninstall_purge_never_deletes_a_stranded_adopted_skill(layout):
    corpus, harness = layout
    _skill(harness, "deploy")
    _adopt(corpus, [harness])
    _skill(harness, "deploy")  # origin occupied: cannot move back
    _skill(corpus, "manual")

    report = lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[], purge=True)

    assert report["adopted_restored"] == []
    assert report["adopted_conflicts"][0]["name"] == "deploy"
    assert (corpus / "deploy" / "SKILL.md").is_file()  # the only copy survives
    assert not (corpus / "manual").exists()
    assert lifecycle.adopted_names(corpus) == ["deploy"]  # still restorable later


def test_uninstall_dry_run_leaves_adopted_skills_in_place(layout):
    corpus, harness = layout
    origin = _skill(harness, "deploy")
    _adopt(corpus, [harness])
    report = lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[], dry_run=True)
    assert report["adopted_restored"] == ["deploy"]
    assert (corpus / "deploy").exists() and not origin.exists()


def test_state_files_written_before_adopt_existed_still_load(layout):
    corpus, _ = layout
    corpus.mkdir()
    old = {"version": 1, "bootstrap": None, "harness_links": {}, "collected_links": {}, "mcp": {}}
    (corpus / lifecycle.STATE_FILE).write_text(json.dumps(old), encoding="utf-8")
    assert lifecycle._load_state(corpus)["adopted"] == {}
    assert lifecycle.adopted_names(corpus) == []


def test_cli_adopt_and_restore(layout, monkeypatch):
    corpus, harness = layout
    origin = _skill(harness, "deploy")
    monkeypatch.setattr(lifecycle.corpus_mod, "CORPUS_PATH", corpus)
    monkeypatch.setattr(lifecycle.sync, "run_sync", lambda **k: {})
    runner = CliRunner()

    declined = runner.invoke(app, ["adopt", "--from", str(harness)], input="n\n")
    assert declined.exit_code == 1 and origin.exists()

    dry = runner.invoke(app, ["adopt", "--from", str(harness), "--dry-run"])
    assert dry.exit_code == 0 and "would adopt: 1" in dry.stdout and origin.exists()

    done = runner.invoke(app, ["adopt", "--from", str(harness), "--yes", "--json"])
    assert done.exit_code == 0
    assert json.loads(done.stdout)["adopted"][0]["name"] == "deploy"
    assert not origin.exists() and (corpus / "deploy").is_dir()

    nothing = runner.invoke(app, ["adopt", "--from", str(harness)])
    assert nothing.exit_code == 0 and "nothing to adopt" in nothing.stdout

    back = runner.invoke(app, ["restore"])
    assert back.exit_code == 0 and "restored: 1" in back.stdout
    assert origin.exists()
