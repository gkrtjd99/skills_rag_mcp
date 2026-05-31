"""Collect skill directories from Claude/Codex installations into ~/.skills/.

Discovers SKILL.md files in known harness locations and creates symlinks at
~/.skills/<skill-name> pointing to each source directory. The original
location keeps owning updates (since it's a symlink).

Sources scanned (in priority order; first wins on name collisions):

1. ~/.skills                           (already-present entries — never touched)
2. ~/.claude/skills/<name>/SKILL.md
3. ~/.claude/plugins/**/skills/<name>/SKILL.md
4. ~/.codex/skills/<name>/SKILL.md
5. ~/.codex/plugins/**/skills/<name>/SKILL.md

A collision is logged but does NOT overwrite — manual cleanup is safer than
silently picking a different version.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import corpus as corpus_mod


@dataclass
class CollectPlanItem:
    name: str
    source: Path
    action: str  # "link", "skip-exists", "skip-collision", "skip-self"
    reason: str = ""


@dataclass
class CollectReport:
    linked: list[str]
    already_present: list[str]
    collisions: list[tuple[str, Path, Path]]  # (name, kept, rejected)
    sources_scanned: list[Path]

    def to_dict(self) -> dict:
        return {
            "linked": self.linked,
            "already_present": self.already_present,
            "collisions": [
                {"name": n, "kept": str(k), "rejected": str(r)}
                for n, k, r in self.collisions
            ],
            "sources_scanned": [str(s) for s in self.sources_scanned],
        }


def default_sources() -> list[Path]:
    """Return the harness skill roots to scan, in priority order.

    Each entry can be either:
      - a directory whose children are skill dirs (~/.claude/skills)
      - a directory to scan recursively for SKILL.md (~/.claude/plugins)
    """
    home = Path.home()
    return [
        home / ".claude" / "skills",
        home / ".claude" / "plugins",
        home / ".codex" / "skills",
        home / ".codex" / "plugins",
    ]


def _iter_skill_dirs(root: Path) -> list[Path]:
    """Find every directory under ``root`` that contains a SKILL.md.

    Sorted by SKILL.md mtime DESCENDING so the newest copy wins under
    "first wins" collision handling. This matters because plugin caches
    keep older versions alongside the latest (e.g. ``vercel/0.42.1`` and
    ``vercel/0.43.0`` both contain a ``skills/`` directory).
    """
    if not root.exists():
        return []
    candidates: list[tuple[float, Path]] = []
    visited: set[str] = set()
    # ``followlinks=True`` because primary skill dirs are often symlinks
    # (e.g. ~/.claude/skills/supabase -> some plugin location). The
    # ``visited`` set guards against symlink cycles.
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        try:
            real = os.path.realpath(dirpath)
        except OSError:
            continue
        if real in visited:
            dirnames[:] = []
            continue
        visited.add(real)
        if "SKILL.md" not in filenames:
            continue
        skill_md = Path(dirpath) / "SKILL.md"
        if not skill_md.is_file():
            continue
        skill_dir = Path(dirpath)
        # Only accept skill directories that sit DIRECTLY inside a
        # ``skills/`` (or ``.skills/``) folder. This drops nested
        # ``skills/<name>/<helper>/SKILL.md`` reference bundles that some
        # plugins ship alongside the real skill, and also drops bare
        # ``skills/SKILL.md`` files.
        parent_name = skill_dir.parent.name if skill_dir.parent else ""
        if parent_name not in {"skills", ".skills"}:
            continue
        try:
            mtime = skill_md.stat().st_mtime
        except OSError:
            mtime = 0.0
        candidates.append((mtime, skill_dir))
    # newest first, then path for stable tie-break
    candidates.sort(key=lambda t: (-t[0], str(t[1])))
    return [p for _, p in candidates]


def plan(
    target: Path | None = None, sources: list[Path] | None = None
) -> tuple[list[CollectPlanItem], CollectReport]:
    """Compute what would be linked. Pure — no filesystem writes."""
    target = (target or corpus_mod.CORPUS_PATH).expanduser()
    sources = sources if sources is not None else default_sources()

    existing: set[str] = set()
    if target.exists():
        for child in target.iterdir():
            existing.add(child.name)

    items: list[CollectPlanItem] = []
    linked: list[str] = []
    already_present: list[str] = []
    collisions: list[tuple[str, Path, Path]] = []
    seen_name_to_source: dict[str, Path] = {}

    for root in sources:
        for skill_dir in _iter_skill_dirs(root):
            name = skill_dir.name

            # Avoid linking ~/.skills back into itself
            try:
                if skill_dir.resolve().is_relative_to(target.resolve()):
                    items.append(
                        CollectPlanItem(
                            name=name, source=skill_dir, action="skip-self"
                        )
                    )
                    continue
            except (OSError, ValueError):
                pass

            if name in existing:
                already_present.append(name)
                items.append(
                    CollectPlanItem(
                        name=name,
                        source=skill_dir,
                        action="skip-exists",
                        reason=f"~/.skills/{name} already exists",
                    )
                )
                continue

            if name in seen_name_to_source:
                kept = seen_name_to_source[name]
                collisions.append((name, kept, skill_dir))
                items.append(
                    CollectPlanItem(
                        name=name,
                        source=skill_dir,
                        action="skip-collision",
                        reason=f"already linked from {kept}",
                    )
                )
                continue

            seen_name_to_source[name] = skill_dir
            linked.append(name)
            items.append(
                CollectPlanItem(name=name, source=skill_dir, action="link")
            )

    report = CollectReport(
        linked=linked,
        already_present=already_present,
        collisions=collisions,
        sources_scanned=sources,
    )
    return items, report


def apply(
    target: Path | None = None,
    sources: list[Path] | None = None,
    dry_run: bool = False,
) -> CollectReport:
    """Plan and then create symlinks. ``dry_run`` performs no writes."""
    target = (target or corpus_mod.CORPUS_PATH).expanduser()
    if not dry_run:
        target.mkdir(parents=True, exist_ok=True)

    items, report = plan(target=target, sources=sources)

    if dry_run:
        return report

    for item in items:
        if item.action != "link":
            continue
        link_path = target / item.name
        try:
            link_path.symlink_to(item.source, target_is_directory=True)
        except FileExistsError:
            # Raced with an external process; treat as already_present.
            pass

    return report
