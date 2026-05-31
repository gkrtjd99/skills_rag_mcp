from __future__ import annotations

from pathlib import Path

from skill_rag import collect


def _write_skill(dirpath: Path, name: str, desc: str = "test skill") -> Path:
    skill_dir = dirpath / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\nbody\n",
        encoding="utf-8",
    )
    return skill_dir


def test_plan_links_new_skills(tmp_path: Path) -> None:
    target = tmp_path / "target"
    src = tmp_path / "claude" / "skills"
    _write_skill(src, "alpha")
    _write_skill(src, "beta")

    _, report = collect.plan(target=target, sources=[src])
    assert sorted(report.linked) == ["alpha", "beta"]


def test_apply_creates_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target"
    src = tmp_path / "claude" / "skills"
    skill_dir = _write_skill(src, "alpha")

    report = collect.apply(target=target, sources=[src])
    link = target / "alpha"
    assert link.is_symlink()
    assert link.resolve() == skill_dir.resolve()
    assert "alpha" in report.linked


def test_existing_target_entry_is_preserved(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "alpha").mkdir()  # pre-existing user-owned dir

    src = tmp_path / "claude" / "skills"
    _write_skill(src, "alpha", desc="from harness")

    report = collect.apply(target=target, sources=[src])
    assert report.linked == []
    assert "alpha" in report.already_present
    # original kept untouched (not a symlink)
    assert not (target / "alpha").is_symlink()


def test_collision_first_wins(tmp_path: Path) -> None:
    target = tmp_path / "target"
    src_a = tmp_path / "claude" / "skills"
    src_b = tmp_path / "codex" / "skills"
    _write_skill(src_a, "shared")
    _write_skill(src_b, "shared", desc="from codex")

    report = collect.apply(target=target, sources=[src_a, src_b])
    assert report.linked == ["shared"]
    assert len(report.collisions) == 1
    name, kept, rejected = report.collisions[0]
    assert name == "shared"
    assert kept.parent == src_a
    assert rejected.parent == src_b


def test_follows_symlinks_in_source(tmp_path: Path) -> None:
    """Common case: ~/.claude/skills/supabase is a symlink to a plugin dir."""
    target = tmp_path / "target"
    real_dir = tmp_path / "plugins" / "supabase"
    real_dir.mkdir(parents=True)
    (real_dir / "SKILL.md").write_text(
        "---\nname: supabase\ndescription: supabase guidance\n---\nbody\n",
        encoding="utf-8",
    )

    src = tmp_path / "claude" / "skills"
    src.mkdir(parents=True)
    (src / "supabase").symlink_to(real_dir, target_is_directory=True)

    report = collect.apply(target=target, sources=[src])
    assert "supabase" in report.linked


def test_nested_helper_skill_md_is_ignored(tmp_path: Path) -> None:
    """skills/<name>/<subdir>/SKILL.md is not a top-level skill."""
    target = tmp_path / "target"
    src = tmp_path / "plugins" / "vercel" / "0.43.0" / "skills"
    _write_skill(src, "ai-sdk")
    _write_skill(src / "ai-sdk", "upstream")

    report = collect.apply(target=target, sources=[src])
    assert report.linked == ["ai-sdk"]


def test_newer_plugin_version_wins(tmp_path: Path) -> None:
    import os
    import time

    target = tmp_path / "target"
    src = tmp_path / "plugins"
    old = src / "vercel" / "0.42.0" / "skills"
    _write_skill(old, "auth", desc="old auth")
    # ensure measurable mtime gap
    time.sleep(0.05)
    new = src / "vercel" / "0.43.0" / "skills"
    new_dir = _write_skill(new, "auth", desc="new auth")
    later = time.time() + 1
    os.utime(new_dir / "SKILL.md", (later, later))

    report = collect.apply(target=target, sources=[src])
    assert report.linked == ["auth"]
    link = target / "auth"
    assert link.resolve() == new_dir.resolve()
