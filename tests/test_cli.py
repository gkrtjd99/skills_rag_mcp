import pytest
import json
from typer.testing import CliRunner

from skill_rag import index as index_mod
from skill_rag import sync as sync_mod
from skill_rag.cli import app
from skill_rag import lifecycle as lifecycle_mod


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_RAG_INDEX_PATH", str(tmp_path / "index.lance"))
    monkeypatch.setenv("SKILL_RAG_CORPUS_PATH", str(tmp_path / "skills"))
    monkeypatch.setenv("SKILL_RAG_SCORE_THRESHOLD", "0.0")
    import importlib
    from skill_rag import corpus, retrieve
    importlib.reload(corpus)
    importlib.reload(index_mod)
    importlib.reload(retrieve)
    importlib.reload(sync_mod)
    yield
    index_mod.reset()
    sync_mod.reset_cache()


def _mk(corpus_root, name, desc="d"):
    d = corpus_root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\nbody\n", encoding="utf-8"
    )


def test_sync_command(tmp_path):
    runner = CliRunner()
    _mk(tmp_path / "skills", "foo")
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0
    assert "added" in result.stdout
    assert "foo" in result.stdout


def test_query_command(tmp_path):
    runner = CliRunner()
    _mk(tmp_path / "skills", "foo", desc="useful skill")
    runner.invoke(app, ["sync"])
    result = runner.invoke(app, ["query", "useful"])
    assert result.exit_code == 0
    assert "foo" in result.stdout


def test_query_no_match(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILL_RAG_SCORE_THRESHOLD", "0.99")
    import importlib
    from skill_rag import corpus, retrieve
    importlib.reload(corpus)
    importlib.reload(retrieve)
    runner = CliRunner()
    _mk(tmp_path / "skills", "foo")
    runner.invoke(app, ["sync"])
    result = runner.invoke(app, ["query", "completely unrelated"])
    assert result.exit_code == 0
    assert "no" in result.stdout.lower()


def test_list_command(tmp_path):
    runner = CliRunner()
    _mk(tmp_path / "skills", "foo")
    _mk(tmp_path / "skills", "bar")
    runner.invoke(app, ["sync"])
    result = runner.invoke(app, ["list-skills"])
    assert result.exit_code == 0
    assert "foo" in result.stdout
    assert "bar" in result.stdout


def test_reset_command(tmp_path):
    runner = CliRunner()
    _mk(tmp_path / "skills", "foo")
    runner.invoke(app, ["sync"])
    result = runner.invoke(app, ["reset"])
    assert result.exit_code == 0
    assert index_mod.list_indexed() == []


def test_uninstall_command_dry_run(tmp_path, monkeypatch):
    runner = CliRunner()
    captured = {}
    def fake(**kwargs):
        captured.update(kwargs)
        return {"mcp": {}, "harness_links_removed": [], "index_dropped": False,
                "corpus": {"removed_links": [], "removed_dirs": [], "kept": []},
                "dry_run": True, "purge": False}
    monkeypatch.setattr(lifecycle_mod, "uninstall", fake)
    result = runner.invoke(app, ["uninstall", "--dry-run"])
    assert result.exit_code == 0
    assert captured["dry_run"] is True


def test_uninstall_command_confirm_decline_aborts(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(lifecycle_mod, "uninstall", lambda **k: pytest.fail("should not run"))
    result = runner.invoke(app, ["uninstall"], input="n\n")
    assert result.exit_code == 1


def test_install_command_invokes_lifecycle(tmp_path, monkeypatch):
    runner = CliRunner()
    called = {}
    def fake_install(**k):
        called["ran"] = True
        return {"bootstrap_installed": True, "harness_links": [],
                "collect_ran": True, "sync_ran": True, "mcp": {}, "dry_run": False}
    monkeypatch.setattr(lifecycle_mod, "install", fake_install)
    result = runner.invoke(app, ["install"])
    assert result.exit_code == 0
    assert called["ran"] is True


def test_uninstall_yes_skips_prompt(tmp_path, monkeypatch):
    runner = CliRunner()
    captured = {}
    def fake(**kwargs):
        captured.update(kwargs)
        return {"mcp": {}, "harness_links_removed": [], "index_dropped": True,
                "corpus": {"removed_links": [], "removed_dirs": [], "kept": []},
                "dry_run": False, "purge": True}
    monkeypatch.setattr(lifecycle_mod, "uninstall", fake)
    result = runner.invoke(app, ["uninstall", "--purge", "--yes"])  # no stdin input
    assert result.exit_code == 0
    assert captured["purge"] is True
    assert captured["dry_run"] is False


def test_install_json_output(tmp_path, monkeypatch):
    runner = CliRunner()
    def fake_install(**k):
        return {"bootstrap_installed": True, "harness_links": [],
                "collect_ran": True, "sync_ran": True, "mcp": {}, "dry_run": False}
    monkeypatch.setattr(lifecycle_mod, "install", fake_install)
    result = runner.invoke(app, ["install", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["bootstrap_installed"] is True


def test_eval_command_uses_explicit_corpus_and_dataset(tmp_path):
    runner = CliRunner()
    corpus = tmp_path / "eval-skills"
    _mk(corpus, "foo", desc="alpha beta testing")
    dataset = tmp_path / "queries.jsonl"
    dataset.write_text('{"query": "alpha beta", "expected": ["foo"]}\n')

    result = runner.invoke(
        app,
        ["eval", "--corpus", str(corpus), "--dataset", str(dataset), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["recall_at_k"] == 1.0
    assert payload["corpus"] == str(corpus.resolve())
    assert payload["dataset"] == str(dataset.resolve())
