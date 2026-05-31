from __future__ import annotations

from pathlib import Path

from .agents import agent_for_path
from .corpus import BOOTSTRAP_SKILL_NAME
from .models import SkillRecord
from .parser import parse_skill_file


def scan(root: Path) -> list[SkillRecord]:
    """Return a SkillRecord for every <root>/<name>/SKILL.md.

    Flat layout only — no recursion into subdirectories below the skill dir.
    Skips the bootstrap skill so it never appears in search results.
    """
    if not root.exists():
        return []
    records: list[SkillRecord] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if child.name == BOOTSTRAP_SKILL_NAME:
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        record = parse_skill_file(skill_md)
        if record is not None:
            # Classify by the symlink target: a corpus entry is usually a
            # symlink into a harness install, so resolve before classifying.
            record.agent = agent_for_path(skill_md.resolve())
            records.append(record)
    return records
