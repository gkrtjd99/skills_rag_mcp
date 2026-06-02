"""Orchestrate install / uninstall. Paths are injectable for testing."""

from __future__ import annotations

import shutil
from pathlib import Path

from . import corpus as corpus_mod
from . import index as index_mod
from . import mcp_config
from . import sync as sync_mod

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_SRC = PROJECT_ROOT / "bootstrap-skill" / corpus_mod.BOOTSTRAP_SKILL_NAME


def default_harness_skill_dirs() -> list[Path]:
    home = Path.home()
    return [home / ".claude" / "skills", home / ".codex" / "skills"]


def _clean_corpus(target: Path, *, purge: bool, dry_run: bool) -> dict:
    removed_links: list[str] = []
    removed_dirs: list[str] = []
    kept: list[str] = []
    if not target.exists():
        return {"removed_links": [], "removed_dirs": [], "kept": []}
    for child in sorted(target.iterdir(), key=lambda p: p.name):
        name = child.name
        is_bootstrap = name == corpus_mod.BOOTSTRAP_SKILL_NAME
        if child.is_symlink():
            if not dry_run:
                child.unlink()
            removed_links.append(name)
        elif purge or is_bootstrap:
            if not dry_run:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            removed_dirs.append(name)
        else:
            kept.append(name)
    return {"removed_links": removed_links, "removed_dirs": removed_dirs, "kept": kept}


def uninstall(
    *,
    purge: bool = False,
    corpus_path: Path | None = None,
    harness_skill_dirs: list[Path] | None = None,
    dry_run: bool = False,
) -> dict:
    corpus_path = (corpus_path or corpus_mod.CORPUS_PATH).expanduser()
    harness_skill_dirs = (
        harness_skill_dirs if harness_skill_dirs is not None else default_harness_skill_dirs()
    )

    mcp = {}
    if not dry_run:
        mcp["claude"] = mcp_config.unregister_claude()
        mcp["codex"] = mcp_config.unregister_codex()

    links_removed: list[str] = []
    for d in harness_skill_dirs:
        link = d / corpus_mod.BOOTSTRAP_SKILL_NAME
        if link.is_symlink():
            if not dry_run:
                link.unlink()
            links_removed.append(str(link))

    if not dry_run:
        index_mod.reset()
        sync_mod.reset_cache()

    corpus_report = _clean_corpus(corpus_path, purge=purge, dry_run=dry_run)
    return {
        "mcp": mcp,
        "harness_links_removed": links_removed,
        "index_dropped": not dry_run,
        "corpus": corpus_report,
        "dry_run": dry_run,
        "purge": purge,
    }
