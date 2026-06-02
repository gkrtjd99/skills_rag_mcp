"""Orchestrate install / uninstall. Paths are injectable for testing."""

from __future__ import annotations

import shutil
from pathlib import Path

from . import collect
from . import corpus as corpus_mod
from . import index as index_mod
from . import mcp_config
from . import sync

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_SRC = PROJECT_ROOT / "bootstrap-skill" / corpus_mod.BOOTSTRAP_SKILL_NAME  # used by install()


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

    if not dry_run:
        mcp: dict = {}
        mcp["claude"] = mcp_config.unregister_claude()
        mcp["codex"] = mcp_config.unregister_codex()
    else:
        mcp = mcp_config.preview_modes()

    links_removed: list[str] = []
    for d in harness_skill_dirs:
        link = d / corpus_mod.BOOTSTRAP_SKILL_NAME
        if link.is_symlink():
            if not dry_run:
                link.unlink()
            links_removed.append(str(link))

    if not dry_run:
        index_mod.reset()
        sync.reset_cache()

    corpus_report = _clean_corpus(corpus_path, purge=purge, dry_run=dry_run)
    return {
        "mcp": mcp,
        "harness_links_removed": links_removed,
        "index_dropped": not dry_run,
        "corpus": corpus_report,
        "dry_run": dry_run,
        "purge": purge,
    }


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _copy_bootstrap(corpus_path: Path, dry_run: bool, refresh: bool) -> tuple[bool, bool]:
    dest = corpus_path / corpus_mod.BOOTSTRAP_SKILL_NAME
    if dest.exists() or dest.is_symlink():
        if not refresh:
            return False, False
        if not dry_run:
            _remove_path(dest)
            corpus_path.mkdir(parents=True, exist_ok=True)
            shutil.copytree(BOOTSTRAP_SRC, dest)
        return False, True
    if not dry_run:
        corpus_path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(BOOTSTRAP_SRC, dest)
    return True, False


def _link_bootstrap(harness_skill_dirs: list[Path], corpus_path: Path, dry_run: bool) -> list[str]:
    target = corpus_path / corpus_mod.BOOTSTRAP_SKILL_NAME
    linked: list[str] = []
    for d in harness_skill_dirs:
        link = d / corpus_mod.BOOTSTRAP_SKILL_NAME
        # resolve() uses strict=False (default): safe even before target exists (dry_run)
        if link.is_symlink() and link.resolve() == target.resolve():
            continue
        if not dry_run:
            d.mkdir(parents=True, exist_ok=True)
            if link.is_symlink() or link.exists():
                if link.is_dir() and not link.is_symlink():
                    shutil.rmtree(link)
                else:
                    link.unlink()
            link.symlink_to(target, target_is_directory=True)
        linked.append(str(link))
    return linked


def install(
    *,
    repo: Path | None = None,
    corpus_path: Path | None = None,
    harness_skill_dirs: list[Path] | None = None,
    dry_run: bool = False,
    refresh_bootstrap: bool = False,
) -> dict:
    """Install bootstrap + collect/index + register MCP. Note: sync.run_sync()
    always indexes the configured corpus (corpus_mod.CORPUS_PATH); a non-default
    corpus_path only affects bootstrap copy/collect/cleanup (test isolation)."""
    repo = (repo or PROJECT_ROOT).expanduser()
    corpus_path = (corpus_path or corpus_mod.CORPUS_PATH).expanduser()
    harness_skill_dirs = (
        harness_skill_dirs if harness_skill_dirs is not None else default_harness_skill_dirs()
    )

    bootstrap_installed, bootstrap_refreshed = _copy_bootstrap(
        corpus_path, dry_run, refresh_bootstrap
    )
    links = _link_bootstrap(harness_skill_dirs, corpus_path, dry_run)

    collect_ran = sync_ran = False
    if not dry_run:
        mcp: dict = {}
        collect.apply(target=corpus_path)
        collect_ran = True
        sync.run_sync()
        sync_ran = True
        mcp["claude"] = mcp_config.register_claude(repo)
        mcp["codex"] = mcp_config.register_codex(repo)
    else:
        mcp = mcp_config.preview_modes()

    return {
        "bootstrap_installed": bootstrap_installed,
        "bootstrap_refreshed": bootstrap_refreshed,
        "harness_links": links,
        "collect_ran": collect_ran,
        "sync_ran": sync_ran,
        "mcp": mcp,
        "dry_run": dry_run,
    }
