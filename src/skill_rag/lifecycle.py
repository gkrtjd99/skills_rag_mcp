"""Orchestrate install / uninstall / adopt / restore. Paths are injectable for testing."""

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
    return {
        "version": 1,
        "bootstrap": None,
        "harness_links": {},
        "collected_links": {},
        "mcp": {},
        "adopted": {},
    }


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
    # Added after version 1 shipped; absent in older state files.
    if not isinstance(state.get("adopted"), dict):
        state["adopted"] = {}
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


def _clean_corpus(
    target: Path, state: dict, *, purge: bool, dry_run: bool, protected: frozenset[str] = frozenset()
) -> dict:
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
        if name in protected:
            # An adopted skill that could not be moved back is the only copy.
            # Not even --purge deletes it.
            kept.append(name)
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

    # Adopted skills go home before anything is removed: the store holds their
    # only copy, so uninstalling must never strand or delete them.
    restore_report = restore(corpus_path=corpus_path, dry_run=dry_run, sync_index=False)
    stranded = frozenset(item["name"] for item in restore_report["conflicts"])
    if not dry_run:
        state = _load_state(corpus_path)  # restore() rewrote the adopted records

    corpus_report = _clean_corpus(
        corpus_path, state, purge=purge, dry_run=dry_run, protected=stranded
    )
    if not dry_run:
        if stranded:
            # Keep only what a later `skill-rag restore` needs.
            leftover = _empty_state()
            leftover["adopted"] = state["adopted"]
            _write_state(corpus_path, leftover)
        else:
            _state_path(corpus_path).unlink(missing_ok=True)
    return {
        "mcp": mcp,
        "harness_links_removed": links_removed,
        "index_dropped": not dry_run,
        "adopted_restored": [item["name"] for item in restore_report["restored"]],
        "adopted_conflicts": restore_report["conflicts"],
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


def bootstrap_outdated(corpus_path: Path | None = None) -> bool:
    """True if the installed bootstrap skill differs from this checkout's template."""
    installed = (corpus_path or corpus_mod.CORPUS_PATH) / corpus_mod.BOOTSTRAP_SKILL_NAME / "SKILL.md"
    template = BOOTSTRAP_SRC / "SKILL.md"
    if not installed.is_file() or not template.is_file():
        return False
    return _hash_file(installed) != _hash_file(template)


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
    collect_skills: bool = True,
) -> dict:
    """Install bootstrap + collect/index + register MCP for one corpus.

    ``collect_skills=False`` skips linking harness and plugin skills into the
    store, for a store that should hold only what the user puts or adopts
    there.
    """
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
        if collect_skills:
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
        "bootstrap_outdated": not bootstrap_refreshed and bootstrap_outdated(corpus_path),
        "harness_links": links,
        "harness_conflicts": harness_conflicts,
        "collect_ran": collect_ran,
        "sync_ran": sync_ran,
        "mcp": mcp,
        "dry_run": dry_run,
    }


# --- adopt / restore: make ~/.skills the only home of a skill ---------------
#
# `collect` leaves a skill where the harness installed it and links to it, so
# the harness keeps loading its description into every session. Adopting moves
# the directory into the store instead: the harness no longer sees it, and the
# skill is served only through search_skills / get_skill.


def _direct_skill_dirs(root: Path) -> list[Path]:
    """``root/<name>`` entries that are skills. No recursion: nested or
    plugin-managed layouts are not this command's to move."""
    if not root.is_dir():
        return []
    return [c for c in sorted(root.iterdir()) if c.is_dir() and (c / "SKILL.md").is_file()]


def adopt(
    *,
    sources: list[Path] | None = None,
    names: list[str] | None = None,
    corpus_path: Path | None = None,
    dry_run: bool = False,
    sync_index: bool = True,
) -> dict:
    """Move skills out of harness (or project) skill directories into the store.

    ``sources`` are skill roots whose direct children are skill directories;
    the default is the user-level harness directories. Every move is recorded
    so ``restore`` and ``uninstall`` can put the skill back where it was.
    Symlinked entries are skipped: something else owns them.
    """
    # Absolute paths: the record must mean the same place whatever directory
    # restore or uninstall is later run from.
    corpus_path = (corpus_path or corpus_mod.CORPUS_PATH).expanduser().absolute()
    sources = sources if sources is not None else default_harness_skill_dirs()
    wanted = set(names) if names else None
    state = _load_state(corpus_path)
    adopted: list[dict] = []
    skipped: list[dict] = []
    planned: set[str] = set()

    for root in sources:
        for source in _direct_skill_dirs(Path(root).expanduser().absolute()):
            name = source.name
            if name == corpus_mod.BOOTSTRAP_SKILL_NAME or (wanted is not None and name not in wanted):
                continue
            dest = corpus_path / name

            def skip(reason: str) -> None:
                skipped.append({"name": name, "source": str(source), "reason": reason})

            if source.is_symlink():
                skip("is a symlink; managed elsewhere")
                continue
            replaces_link = False
            if dest.is_symlink():
                # `collect` linked this very directory earlier: swap the link
                # for the real thing.
                if dest.resolve() != source.resolve():
                    skip(f"{dest} links to a different skill")
                    continue
                replaces_link = True
            elif dest.exists() or name in planned:
                skip(f"{dest} already exists")
                continue

            planned.add(name)
            adopted.append({"name": name, "origin": str(source)})
            if dry_run:
                continue
            # Record intent first: if the move is interrupted, restore() can
            # still tell where the skill belongs.
            state["adopted"][name] = {"origin": str(source), "store": str(dest)}
            if replaces_link:
                state["collected_links"].pop(str(dest), None)
            _write_state(corpus_path, state)
            if replaces_link:
                dest.unlink()
            corpus_path.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(dest))

    sync_ran = False
    if adopted and not dry_run and sync_index:
        sync.run_sync(corpus_path=corpus_path)
        sync_ran = True
    return {"adopted": adopted, "skipped": skipped, "sync_ran": sync_ran, "dry_run": dry_run}


def restore(
    *,
    names: list[str] | None = None,
    corpus_path: Path | None = None,
    dry_run: bool = False,
    sync_index: bool = True,
) -> dict:
    """Move adopted skills back to where ``adopt`` found them.

    A skill whose original location is occupied again stays in the store and
    is reported as a conflict; nothing is overwritten.
    """
    corpus_path = (corpus_path or corpus_mod.CORPUS_PATH).expanduser()
    wanted = set(names) if names else None
    state = _load_state(corpus_path)
    restored: list[dict] = []
    conflicts: list[dict] = []

    for name, record in sorted(state["adopted"].items()):
        if wanted is not None and name not in wanted:
            continue
        store, origin = Path(record["store"]), Path(record["origin"])
        occupied = origin.exists() or origin.is_symlink()
        if not store.exists():
            if not occupied:
                conflicts.append({"name": name, "origin": str(origin), "reason": "missing from the store"})
                continue
            # Already back (interrupted adopt, or moved by hand): just forget it.
        elif occupied:
            conflicts.append({"name": name, "origin": str(origin), "reason": "original location is occupied"})
            continue
        restored.append({"name": name, "origin": str(origin)})
        if dry_run:
            continue
        if store.exists():
            origin.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(store), str(origin))
        del state["adopted"][name]
        _write_state(corpus_path, state)

    sync_ran = False
    if restored and not dry_run and sync_index:
        sync.run_sync(corpus_path=corpus_path)
        sync_ran = True
    return {"restored": restored, "conflicts": conflicts, "sync_ran": sync_ran, "dry_run": dry_run}


def adopted_names(corpus_path: Path | None = None) -> list[str]:
    corpus_path = (corpus_path or corpus_mod.CORPUS_PATH).expanduser()
    return sorted(_load_state(corpus_path)["adopted"])
