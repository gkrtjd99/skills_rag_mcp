from pathlib import Path

import tomlkit

from skill_rag import mcp_config


def test_register_codex_adds_block(tmp_path):
    cfg = tmp_path / "config.toml"
    repo = tmp_path / "repo"

    changed = mcp_config.register_codex(repo, path=cfg)

    assert changed is True
    doc = tomlkit.parse(cfg.read_text())
    entry = doc["mcp_servers"]["skill-rag"]
    assert entry["command"] == "uv"
    assert entry["args"] == ["--directory", str(repo), "run", "skill-rag", "mcp"]


def test_register_codex_preserves_other_entries(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[mcp_servers.other]\ncommand = "foo"\nargs = ["bar"]\n', encoding="utf-8"
    )
    repo = tmp_path / "repo"

    mcp_config.register_codex(repo, path=cfg)

    doc = tomlkit.parse(cfg.read_text())
    assert doc["mcp_servers"]["other"]["command"] == "foo"
    assert "skill-rag" in doc["mcp_servers"]


def test_register_codex_is_idempotent(tmp_path):
    cfg = tmp_path / "config.toml"
    repo = tmp_path / "repo"
    assert mcp_config.register_codex(repo, path=cfg) is True
    assert mcp_config.register_codex(repo, path=cfg) is False


def test_unregister_codex_removes_block(tmp_path):
    cfg = tmp_path / "config.toml"
    repo = tmp_path / "repo"
    mcp_config.register_codex(repo, path=cfg)

    changed = mcp_config.unregister_codex(path=cfg)

    assert changed is True
    doc = tomlkit.parse(cfg.read_text())
    assert "skill-rag" not in doc.get("mcp_servers", {})


def test_unregister_codex_absent_is_noop(tmp_path):
    cfg = tmp_path / "config.toml"
    assert mcp_config.unregister_codex(path=cfg) is False
