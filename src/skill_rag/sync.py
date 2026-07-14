"""Reconcile the LanceDB index against the corpus directory.

Only this module holds mutable state (a single timestamp).
"""

from __future__ import annotations

from time import monotonic as _monotonic
from threading import RLock
from pathlib import Path

from . import corpus as corpus_mod
from . import index as index_mod
from . import loader
from . import translate as translate_mod

_last_sync_at: float | None = None
_sync_lock = RLock()


def _dedupe_by_name(records: list) -> tuple[list, list[dict[str, str]]]:
    """Keep the first record for each frontmatter name; report skipped duplicates."""
    seen: dict[str, str] = {}
    kept = []
    duplicates: list[dict[str, str]] = []
    for record in records:
        kept_path = seen.get(record.name)
        if kept_path is not None:
            duplicates.append(
                {"name": record.name, "kept": kept_path, "skipped": record.path}
            )
            continue
        seen[record.name] = record.path
        kept.append(record)
    return kept, duplicates


def _fill_translation(record) -> None:
    text, status = translate_mod.translate_for_index(record.description)
    record.description_translated = text
    record.translation_status = status


def _needs_translation_retry(row: dict, record) -> bool:
    if not translate_mod.TRANSLATE_ENABLED:
        return False
    if not translate_mod.is_translatable(record.description):
        return False
    return row.get("translation_status", "failed") in {"failed", "disabled", "pending"}


def run_sync(corpus_path: Path | None = None) -> dict:
    """Run one sync while preventing concurrent index mutations in-process."""
    with _sync_lock:
        return _run_sync(corpus_path)


def _run_sync(corpus_path: Path | None = None) -> dict:
    """Force a sync for ``corpus_path`` (or the configured global corpus).

    The optional path keeps lifecycle operations testable and internally
    consistent: collection and indexing always operate on the same corpus.
    Runtime MCP calls continue to use the one configured global corpus.
    """
    global _last_sync_at
    corpus_path = (corpus_path or corpus_mod.CORPUS_PATH).expanduser()
    records, duplicate_names = _dedupe_by_name(loader.scan(corpus_path))
    indexed_rows = {row["path"]: row for row in index_mod.list_indexed()}
    disk_paths = {r.path for r in records}

    added: list[str] = []
    updated: list[str] = []
    translation_retried: list[str] = []
    to_upsert = []
    unchanged = 0
    for r in records:
        prev_row = indexed_rows.get(r.path)
        if prev_row is None:
            added.append(r.name)
            to_upsert.append(r)
        elif prev_row["content_hash"] != r.content_hash:
            updated.append(r.name)
            to_upsert.append(r)
        elif _needs_translation_retry(prev_row, r):
            translation_retried.append(r.name)
            to_upsert.append(r)
        else:
            unchanged += 1

    removed_paths = [p for p in indexed_rows if p not in disk_paths]
    # Recover names by querying the indexed rows we just listed.
    removed_names: list[str] = []
    if removed_paths:
        for row in index_mod.list_indexed():
            if row["path"] in removed_paths:
                removed_names.append(row["name"])

    if to_upsert:
        for record in to_upsert:
            _fill_translation(record)
        index_mod.upsert(to_upsert)
    if removed_paths:
        index_mod.delete_by_paths(removed_paths)

    _last_sync_at = _monotonic()
    return {
        "added": added,
        "updated": updated,
        "removed": removed_names,
        "unchanged": unchanged,
        "translation_retried": translation_retried,
        "duplicate_names": duplicate_names,
    }


def sync_if_stale(ttl: float | None = None) -> None:
    """Run sync only if the last run was longer than ``ttl`` seconds ago.

    Pass ``ttl=0`` to force a sync regardless of cache age.
    """
    global _last_sync_at
    with _sync_lock:
        if ttl is None:
            ttl = corpus_mod.SYNC_TTL_SECONDS
        now = _monotonic()
        if ttl > 0 and _last_sync_at is not None and (now - _last_sync_at) < ttl:
            return
        run_sync()


def reset_cache() -> None:
    """Clear the TTL timestamp. Next sync_if_stale call will run."""
    global _last_sync_at
    with _sync_lock:
        _last_sync_at = None
