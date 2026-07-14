"""Orchestrate install / uninstall. Paths are injectable for testing."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path

from . import collect
from . import corpus as corpus_mod
from . import index as index_mod
from . import mcp_config
from . import sync

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_SRC = PROJECT_ROOT / "bootstrap-skill" / corpus_mod.BOOTSTRAP_SKILL_NAME  # used by install()
STATE_FILE = ".skill-rag-install-state.json"
BOOTSTRAP_OWNER_MARKER = ".skill-rag-install-owner"


def _state_path(corpus_path: Path) -> Path:
    return corpus_path / STATE_FILE


def _empty_state() -> dict:
    return {"version": 1, "bootstrap": None, "harness_links": {}, "collected_links": {}, "mcp": {}}


def _load_state(corpus_path: Path) -> dict:
    try:
        state = json.loads(_state_path(corpus_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    if not isinstance(state, dict) or state.get("version") != 1:
        return _empty_state()
    for key in ("harness_links", "collected_links", "mcp"):
        if not isinstance(state.get(key), dict):
            return _empty_state()
    return state


def _write_state(corpus_path: Path, state: dict) -> None:
    path = _state_path(corpus_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _hash_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _marker_matches(path: Path, token: str | None) -> bool:
    try:
        return token is not None and path.read_text(encoding="utf-8") == token
    except OSError:
        return False


def _link_matches(path: Path, expected_target: str) -> bool:
    try:
        return path.is_symlink() and str(path.resolve()) == expected_target
    except OSError:
        return False


def default_harness_skill_dirs() -> list[Path]:
    home = Path.home()
    return [home / ".claude" / "skills", home / ".codex" / "skills"]


def _clean_corpus(target: Path, state: dict, *, purge: bool, dry_run: bool) -> dict:
    removed_links: list[str] = []
    removed_dirs: list[str] = []
    kept: list[str] = []
    if not target.exists():
        return {"removed_links": [], "removed_dirs": [], "kept": []}
    for child in sorted(target.iterdir(), key=lambda p: p.name):
        name = child.name
        is_bootstrap = name == corpus_mod.BOOTSTRAP_SKILL_NAME
        if child.name == STATE_FILE:
            continue
        expected = state["collected_links"].get(str(child))
        bootstrap = state.get("bootstrap") or {}
        is_owned_bootstrap = (
            str(child) == bootstrap.get("path")
            and _hash_file(child / "SKILL.md") == bootstrap.get("skill_hash")
            and _marker_matches(child / BOOTSTRAP_OWNER_MARKER, bootstrap.get("owner_token"))
        )
        if child.is_symlink() and (purge or (expected and _link_matches(child, expected))):
            if not dry_run:
                child.unlink()
            removed_links.append(name)
        elif purge or (is_bootstrap and is_owned_bootstrap):
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
    state = _load_state(corpus_path)
    harness_skill_dirs = (
        harness_skill_dirs if harness_skill_dirs is not None else default_harness_skill_dirs()
    )

    if not dry_run:
        mcp: dict = {}
        mcp["claude"] = mcp_config.unregister_claude() if state["mcp"].get("claude") else "noop"
        mcp["codex"] = mcp_config.unregister_codex() if state["mcp"].get("codex") else False
    else:
        mcp = mcp_config.preview_modes()

    links_removed: list[str] = []
    for d in harness_skill_dirs:
        link = d / corpus_mod.BOOTSTRAP_SKILL_NAME
        expected = state["harness_links"].get(str(link))
        if expected and _link_matches(link, expected):
            if not dry_run:
                link.unlink()
            links_removed.append(str(link))

    if not dry_run:
        index_mod.reset()
        sync.reset_cache()

    corpus_report = _clean_corpus(corpus_path, state, purge=purge, dry_run=dry_run)
    if not dry_run:
        _state_path(corpus_path).unlink(missing_ok=True)
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


def _link_bootstrap(harness_skill_dirs: list[Path], corpus_path: Path, dry_run: bool) -> tuple[list[str], list[str]]:
    target = corpus_path / corpus_mod.BOOTSTRAP_SKILL_NAME
    linked: list[str] = []
    conflicts: list[str] = []
    for d in harness_skill_dirs:
        link = d / corpus_mod.BOOTSTRAP_SKILL_NAME
        # resolve() uses strict=False (default): safe even before target exists (dry_run)
        if link.is_symlink() and link.resolve() == target.resolve():
            continue
        if link.is_symlink() or link.exists():
            conflicts.append(str(link))
            continue
        if not dry_run:
            d.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target, target_is_directory=True)
        linked.append(str(link))
    return linked, conflicts


def install(
    *,
    repo: Path | None = None,
    corpus_path: Path | None = None,
    harness_skill_dirs: list[Path] | None = None,
    dry_run: bool = False,
    refresh_bootstrap: bool = False,
) -> dict:
    """Install bootstrap + collect/index + register MCP for one corpus."""
    repo = (repo or PROJECT_ROOT).expanduser()
    corpus_path = (corpus_path or corpus_mod.CORPUS_PATH).expanduser()
    harness_skill_dirs = (
        harness_skill_dirs if harness_skill_dirs is not None else default_harness_skill_dirs()
    )

    bootstrap_installed, bootstrap_refreshed = _copy_bootstrap(
        corpus_path, dry_run, refresh_bootstrap
    )
    state = _load_state(corpus_path)
    links, harness_conflicts = _link_bootstrap(harness_skill_dirs, corpus_path, dry_run)

    collect_ran = sync_ran = False
    if not dry_run:
        mcp: dict = {}
        _, collect_report = collect.plan(target=corpus_path)
        collect.apply(target=corpus_path)
        collect_ran = True
        for name in collect_report.linked:
            link = corpus_path / name
            if link.is_symlink():
                state["collected_links"][str(link)] = str(link.resolve())
        for link in links:
            state["harness_links"][link] = str(
                (corpus_path / corpus_mod.BOOTSTRAP_SKILL_NAME).resolve()
            )
        bootstrap = corpus_path / corpus_mod.BOOTSTRAP_SKILL_NAME
        if bootstrap_installed or bootstrap_refreshed:
            token = uuid.uuid4().hex
            (bootstrap / BOOTSTRAP_OWNER_MARKER).write_text(token, encoding="utf-8")
            state["bootstrap"] = {
                "path": str(bootstrap),
                "skill_hash": _hash_file(bootstrap / "SKILL.md"),
                "owner_token": token,
            }
        _write_state(corpus_path, state)
        sync.run_sync(corpus_path=corpus_path)
        sync_ran = True
        mcp["claude"] = mcp_config.register_claude(repo)
        mcp["codex"] = mcp_config.register_codex(repo)
        state["mcp"] = {"claude": mcp["claude"] == "file", "codex": mcp["codex"] is True}
        _write_state(corpus_path, state)
    else:
        mcp = mcp_config.preview_modes()

    return {
        "bootstrap_installed": bootstrap_installed,
        "bootstrap_refreshed": bootstrap_refreshed,
        "harness_links": links,
        "harness_conflicts": harness_conflicts,
        "collect_ran": collect_ran,
        "sync_ran": sync_ran,
        "mcp": mcp,
        "dry_run": dry_run,
    }
