import json
from pathlib import Path

import pytest
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
    assert entry["args"] == mcp_config.launch_args(repo)


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


def test_register_codex_updates_stale_repo(tmp_path):
    cfg = tmp_path / "config.toml"
    mcp_config.register_codex(tmp_path / "old_repo", path=cfg)
    changed = mcp_config.register_codex(tmp_path / "new_repo", path=cfg)
    assert changed is True
    doc = tomlkit.parse(cfg.read_text())
    assert str(tmp_path / "new_repo") in doc["mcp_servers"]["skill-rag"]["args"]


def test_register_codex_rejects_malformed_toml(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("this is = = not valid toml [[[", encoding="utf-8")
    with pytest.raises(ValueError):
        mcp_config.register_codex(tmp_path / "repo", path=cfg)


def test_register_claude_file_fallback(tmp_path):
    cfg = tmp_path / ".claude.json"
    repo = tmp_path / "repo"

    # which() returns None -> no CLI -> file path
    mode = mcp_config.register_claude(
        repo, json_path=cfg, which=lambda _: None
    )

    assert mode == "file"
    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["skill-rag"]["command"] == "uv"
    assert data["mcpServers"]["skill-rag"]["args"] == [
        "--directory", str(repo), "run", "skill-rag", "mcp",
    ]


def test_register_claude_file_preserves_other_servers(tmp_path):
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "foo": 1}))
    repo = tmp_path / "repo"

    mcp_config.register_claude(repo, json_path=cfg, which=lambda _: None)

    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["foo"] == 1
    assert "skill-rag" in data["mcpServers"]


def test_register_claude_uses_cli_when_available(tmp_path):
    calls = []
    repo = tmp_path / "repo"

    mode = mcp_config.register_claude(
        repo,
        json_path=tmp_path / ".claude.json",
        which=lambda name: "/usr/bin/claude",
        run=lambda argv, **kw: calls.append(argv),
    )

    assert mode == "cli"
    verbs = [c[:4] for c in calls]
    assert ["claude", "mcp", "remove", "skill-rag"] in verbs  # idempotent pre-clean
    assert ["claude", "mcp", "add", "skill-rag"] in verbs
    assert verbs.index(["claude", "mcp", "remove", "skill-rag"]) < verbs.index(["claude", "mcp", "add", "skill-rag"])
    assert not (tmp_path / ".claude.json").exists()  # file not touched


def test_unregister_claude_file(tmp_path):
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"skill-rag": {"command": "uv"}}}))

    mode = mcp_config.unregister_claude(json_path=cfg, which=lambda _: None)

    assert mode == "file"
    assert "skill-rag" not in json.loads(cfg.read_text()).get("mcpServers", {})


def test_unregister_claude_cli(tmp_path):
    calls = []
    mode = mcp_config.unregister_claude(
        json_path=tmp_path / ".claude.json",
        which=lambda _: "/usr/bin/claude",
        run=lambda argv, **kw: calls.append(argv),
    )
    assert mode == "cli"
    assert calls[0][:4] == ["claude", "mcp", "remove", "skill-rag"]


def test_register_claude_file_is_idempotent(tmp_path):
    cfg = tmp_path / ".claude.json"
    repo = tmp_path / "repo"
    assert mcp_config.register_claude(repo, json_path=cfg, which=lambda _: None) == "file"
    assert mcp_config.register_claude(repo, json_path=cfg, which=lambda _: None) == "noop"


def test_register_claude_rejects_malformed_json(tmp_path):
    cfg = tmp_path / ".claude.json"
    cfg.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="Cannot parse"):
        mcp_config.register_claude(tmp_path / "repo", json_path=cfg, which=lambda _: None)
