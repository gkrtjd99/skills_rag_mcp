"""Register / unregister the skill-rag MCP server per harness.

All paths are injectable so tests run against tmp dirs. Claude Code prefers
its official CLI (`claude mcp add/remove`); Codex has no such CLI so its
TOML config is edited directly via tomlkit (format-preserving).
"""

from __future__ import annotations

import os
from pathlib import Path

import tomlkit

MCP_NAME = "skill-rag"


def launch_args(repo: Path) -> list[str]:
    """Args after `uv` for launching the MCP server: `uv --directory <repo> run skill-rag mcp`."""
    return ["--directory", str(repo), "run", "skill-rag", "mcp"]


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _backup(path: Path) -> None:
    # Single-slot backup: each write overwrites the previous .bak. One level is
    # enough for a dev tool; do not "fix" this into versioned backups.
    if path.exists():
        _atomic_write(path.with_name(path.name + ".bak"), path.read_text(encoding="utf-8"))


# ----- Codex (~/.codex/config.toml) -------------------------------------

def codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def register_codex(repo: Path, path: Path | None = None) -> bool:
    """Add [mcp_servers.skill-rag]. Returns True if the file changed."""
    path = path or codex_config_path()
    if path.exists():
        try:
            doc = tomlkit.parse(path.read_text(encoding="utf-8"))
        except tomlkit.exceptions.ParseError as exc:
            raise ValueError(f"Cannot parse {path}: {exc}") from exc
    else:
        doc = tomlkit.document()

    desired_args = launch_args(repo)
    existing = doc.get("mcp_servers", {})
    if MCP_NAME in existing:
        cur = existing[MCP_NAME]
        if cur.get("command") == "uv" and list(cur.get("args", [])) == desired_args:
            return False

    if "mcp_servers" not in doc:
        doc["mcp_servers"] = tomlkit.table(is_super_table=True)
    entry = tomlkit.table()
    entry["command"] = "uv"
    entry["args"] = desired_args
    doc["mcp_servers"][MCP_NAME] = entry

    _backup(path)
    _atomic_write(path, tomlkit.dumps(doc))
    return True


def unregister_codex(path: Path | None = None) -> bool:
    """Remove [mcp_servers.skill-rag]. Returns True if the file changed."""
    path = path or codex_config_path()
    if not path.exists():
        return False
    try:
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    except tomlkit.exceptions.ParseError as exc:
        raise ValueError(f"Cannot parse {path}: {exc}") from exc
    if MCP_NAME not in doc.get("mcp_servers", {}):
        return False
    del doc["mcp_servers"][MCP_NAME]
    if len(doc["mcp_servers"]) == 0:
        del doc["mcp_servers"]
    _backup(path)
    _atomic_write(path, tomlkit.dumps(doc))
    return True
