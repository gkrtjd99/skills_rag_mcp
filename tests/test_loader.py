from pathlib import Path

from skill_rag.loader import scan


def _mk(root: Path, name: str, fm_name: str | None = None, desc: str = "d", body: str = "b"):
    d = root / name
    d.mkdir(parents=True)
    nm = fm_name if fm_name is not None else name
    (d / "SKILL.md").write_text(
        f"---\nname: {nm}\ndescription: {desc}\n---\n{body}\n", encoding="utf-8"
    )


def test_scan_empty_dir_returns_empty(tmp_path):
    assert scan(tmp_path) == []


def test_scan_nonexistent_returns_empty(tmp_path):
    assert scan(tmp_path / "missing") == []


def test_scan_finds_skills(tmp_path):
    _mk(tmp_path, "foo")
    _mk(tmp_path, "bar")
    names = sorted(r.name for r in scan(tmp_path))
    assert names == ["bar", "foo"]


def test_scan_skips_bootstrap_skill(tmp_path):
    _mk(tmp_path, "using-skill-rag", desc="bootstrap")
    _mk(tmp_path, "real-skill")
    names = [r.name for r in scan(tmp_path)]
    assert "using-skill-rag" not in names
    assert "real-skill" in names


def test_scan_skips_bootstrap_when_only_frontmatter_name_matches(tmp_path):
    _mk(tmp_path, "renamed-bootstrap", fm_name="using-skill-rag", desc="bootstrap")
    _mk(tmp_path, "real-skill")

    names = [r.name for r in scan(tmp_path)]

    assert names == ["real-skill"]


def test_scan_skips_invalid_utf8_and_keeps_valid_skills(tmp_path):
    _mk(tmp_path, "valid")
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "SKILL.md").write_bytes(b"---\nname: broken\ndescription: \xff\n---\n")

    assert [r.name for r in scan(tmp_path)] == ["valid"]


def test_scan_ignores_dir_without_skill_md(tmp_path):
    (tmp_path / "empty-dir").mkdir()
    _mk(tmp_path, "real-skill")
    names = [r.name for r in scan(tmp_path)]
    assert names == ["real-skill"]


def test_scan_ignores_files_at_root(tmp_path):
    (tmp_path / "loose-file.md").write_text("---\nname: x\ndescription: y\n---\n")
    _mk(tmp_path, "real-skill")
    names = [r.name for r in scan(tmp_path)]
    assert names == ["real-skill"]
