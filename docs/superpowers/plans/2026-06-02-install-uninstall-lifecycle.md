# Install / Uninstall Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add symmetric `install` / `uninstall` lifecycle commands driven by a Makefile, replacing `scripts/install.sh`, with MCP registration that prefers the official CLI and falls back to config-file edits.

**Architecture:** Logic lives in two new testable Python modules — `mcp_config.py` (per-harness MCP registration) and `lifecycle.py` (orchestration) — exposed through new `skill-rag install` / `skill-rag uninstall` CLI commands. A thin `Makefile` wraps `uv run skill-rag ...`. All filesystem/config paths are injectable so tests run against `tmp_path`.

**Tech Stack:** Python 3.13, typer, uv, lancedb, `tomlkit` (new), pytest.

**Baseline note:** HEAD (`feat/install-uninstall-lifecycle`) has NO `clean` command — the earlier `clean` working-tree edits were reverted. This plan adds `install`/`uninstall` fresh; there is nothing named `clean` to remove.

---

### Task 1: Add the `tomlkit` dependency + reference doc

**Files:**
- Modify: `pyproject.toml:9-16`
- Create: `docs/references/tomlkit-llms.txt`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add `tomlkit` to the `dependencies` list:

```toml
dependencies = [
    "lancedb>=0.27.0",
    "sentence-transformers>=5.0.0",
    "pyyaml>=6.0.2",
    "typer>=0.20.0",
    "mcp>=1.20.0",
    "pyarrow>=23.0.0",
    "tomlkit>=0.13.0",
]
```

- [ ] **Step 2: Sync the environment**

Run: `uv sync`
Expected: resolves and installs `tomlkit` (exit 0).

- [ ] **Step 3: Add the reference doc**

Create `docs/references/tomlkit-llms.txt`:

```
# tomlkit quick reference

Format-preserving TOML for Python. Used by skill_rag to add/remove the
[mcp_servers.skill-rag] block in ~/.codex/config.toml without disturbing
the user's other entries, comments, or formatting.

import tomlkit

doc = tomlkit.parse(text)          # parse existing file (preserves layout)
doc = tomlkit.document()           # new empty document

# Nested header [mcp_servers.skill-rag] without an empty [mcp_servers] line:
servers = tomlkit.table(is_super_table=True)
doc["mcp_servers"] = servers
entry = tomlkit.table()
entry["command"] = "uv"
entry["args"] = ["--directory", "/repo", "run", "skill-rag", "mcp"]
servers["skill-rag"] = entry

del doc["mcp_servers"]["skill-rag"]  # remove a block
text = tomlkit.dumps(doc)            # serialize back to a string
"skill-rag" in doc.get("mcp_servers", {})  # membership test
```

- [ ] **Step 4: Verify the import works**

Run: `uv run python -c "import tomlkit; print(tomlkit.__version__)"`
Expected: prints a version (exit 0).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock docs/references/tomlkit-llms.txt
git commit -m "build: add tomlkit dependency for TOML config edits"
```

---

### Task 2: `mcp_config` — shared helpers + Codex (tomlkit)

**Files:**
- Create: `src/skill_rag/mcp_config.py`
- Test: `tests/test_mcp_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_mcp_config.py`:

```python
from pathlib import Path

import tomlkit

from skill_rag import mcp_config


def test_register_codex_adds_block(tmp_path):
    cfg = tmp_path / "config.toml"
    repo = tmp_path / "repo"

    changed = mcp_config.register_codex(repo, path=cfg)

    assert changed is True
    doc = tomlkit.parse(cfg.read_text())
    entry = doc["mcp_servers"]["skill-rag"]
    assert entry["command"] == "uv"
    assert entry["args"] == ["--directory", str(repo), "run", "skill-rag", "mcp"]


def test_register_codex_preserves_other_entries(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[mcp_servers.other]\ncommand = "foo"\nargs = ["bar"]\n', encoding="utf-8"
    )
    repo = tmp_path / "repo"

    mcp_config.register_codex(repo, path=cfg)

    doc = tomlkit.parse(cfg.read_text())
    assert doc["mcp_servers"]["other"]["command"] == "foo"
    assert "skill-rag" in doc["mcp_servers"]


def test_register_codex_is_idempotent(tmp_path):
    cfg = tmp_path / "config.toml"
    repo = tmp_path / "repo"
    assert mcp_config.register_codex(repo, path=cfg) is True
    assert mcp_config.register_codex(repo, path=cfg) is False


def test_unregister_codex_removes_block(tmp_path):
    cfg = tmp_path / "config.toml"
    repo = tmp_path / "repo"
    mcp_config.register_codex(repo, path=cfg)

    changed = mcp_config.unregister_codex(path=cfg)

    assert changed is True
    doc = tomlkit.parse(cfg.read_text())
    assert "skill-rag" not in doc.get("mcp_servers", {})


def test_unregister_codex_absent_is_noop(tmp_path):
    cfg = tmp_path / "config.toml"
    assert mcp_config.unregister_codex(path=cfg) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_mcp_config.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'skill_rag.mcp_config'`).

- [ ] **Step 3: Write the implementation**

Create `src/skill_rag/mcp_config.py`:

```python
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
    return ["--directory", str(repo), "run", "skill-rag", "mcp"]


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _backup(path: Path) -> None:
    if path.exists():
        _atomic_write(path.with_name(path.name + ".bak"), path.read_text(encoding="utf-8"))


# ----- Codex (~/.codex/config.toml) -------------------------------------

def codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def register_codex(repo: Path, path: Path | None = None) -> bool:
    """Add [mcp_servers.skill-rag]. Returns True if the file changed."""
    path = path or codex_config_path()
    doc = tomlkit.parse(path.read_text(encoding="utf-8")) if path.exists() else tomlkit.document()

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
    doc = tomlkit.parse(path.read_text(encoding="utf-8"))
    if MCP_NAME not in doc.get("mcp_servers", {}):
        return False
    del doc["mcp_servers"][MCP_NAME]
    if len(doc["mcp_servers"]) == 0:
        del doc["mcp_servers"]
    _backup(path)
    _atomic_write(path, tomlkit.dumps(doc))
    return True
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_mcp_config.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/skill_rag/mcp_config.py tests/test_mcp_config.py
git commit -m "feat(mcp): register/unregister Codex MCP entry via tomlkit"
```

---

### Task 3: `mcp_config` — Claude (CLI-first, file fallback)

**Files:**
- Modify: `src/skill_rag/mcp_config.py`
- Test: `tests/test_mcp_config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mcp_config.py`:

```python
import json


def test_register_claude_file_fallback(tmp_path):
    cfg = tmp_path / ".claude.json"
    repo = tmp_path / "repo"

    # which() returns None -> no CLI -> file path
    mode = mcp_config.register_claude(
        repo, json_path=cfg, which=lambda _: None
    )

    assert mode == "file"
    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["skill-rag"]["command"] == "uv"
    assert data["mcpServers"]["skill-rag"]["args"] == [
        "--directory", str(repo), "run", "skill-rag", "mcp",
    ]


def test_register_claude_file_preserves_other_servers(tmp_path):
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "foo": 1}))
    repo = tmp_path / "repo"

    mcp_config.register_claude(repo, json_path=cfg, which=lambda _: None)

    data = json.loads(cfg.read_text())
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["foo"] == 1
    assert "skill-rag" in data["mcpServers"]


def test_register_claude_uses_cli_when_available(tmp_path):
    calls = []
    repo = tmp_path / "repo"

    mode = mcp_config.register_claude(
        repo,
        json_path=tmp_path / ".claude.json",
        which=lambda name: "/usr/bin/claude",
        run=lambda argv, **kw: calls.append(argv),
    )

    assert mode == "cli"
    assert calls and calls[0][:4] == ["claude", "mcp", "add", "skill-rag"]
    assert not (tmp_path / ".claude.json").exists()  # file not touched


def test_unregister_claude_file(tmp_path):
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"skill-rag": {"command": "uv"}}}))

    mode = mcp_config.unregister_claude(json_path=cfg, which=lambda _: None)

    assert mode == "file"
    assert "skill-rag" not in json.loads(cfg.read_text()).get("mcpServers", {})


def test_unregister_claude_cli(tmp_path):
    calls = []
    mode = mcp_config.unregister_claude(
        json_path=tmp_path / ".claude.json",
        which=lambda _: "/usr/bin/claude",
        run=lambda argv, **kw: calls.append(argv),
    )
    assert mode == "cli"
    assert calls[0][:4] == ["claude", "mcp", "remove", "skill-rag"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_mcp_config.py -k claude -q`
Expected: FAIL (`module 'skill_rag.mcp_config' has no attribute 'register_claude'`).

- [ ] **Step 3: Write the implementation**

Add to `src/skill_rag/mcp_config.py` (imports at top: add `import json`, `import shutil`, `import subprocess`):

```python
def claude_json_path() -> Path:
    return Path.home() / ".claude.json"


def _claude_cli_add(repo: Path, run) -> None:
    run(
        ["claude", "mcp", "add", MCP_NAME, "--scope", "user", "--", "uv", *launch_args(repo)],
        check=True,
    )


def _claude_cli_remove(run) -> None:
    run(["claude", "mcp", "remove", MCP_NAME, "--scope", "user"], check=False)


def register_claude(repo: Path, json_path: Path | None = None, which=shutil.which, run=subprocess.run) -> str:
    """Returns 'cli' | 'file' | 'noop'."""
    if which("claude"):
        _claude_cli_add(repo, run)
        return "cli"
    json_path = json_path or claude_json_path()
    data = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
    servers = data.setdefault("mcpServers", {})
    desired = {"command": "uv", "args": launch_args(repo)}
    if servers.get(MCP_NAME) == desired:
        return "noop"
    servers[MCP_NAME] = desired
    _backup(json_path)
    _atomic_write(json_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return "file"


def unregister_claude(json_path: Path | None = None, which=shutil.which, run=subprocess.run) -> str:
    """Returns 'cli' | 'file' | 'noop'."""
    if which("claude"):
        _claude_cli_remove(run)
        return "cli"
    json_path = json_path or claude_json_path()
    if not json_path.exists():
        return "noop"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if MCP_NAME not in data.get("mcpServers", {}):
        return "noop"
    del data["mcpServers"][MCP_NAME]
    _backup(json_path)
    _atomic_write(json_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return "file"
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_mcp_config.py -q`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/skill_rag/mcp_config.py tests/test_mcp_config.py
git commit -m "feat(mcp): register/unregister Claude MCP entry, CLI-first"
```

---

### Task 4: `lifecycle.uninstall` — corpus + index + harness links + MCP

**Files:**
- Create: `src/skill_rag/lifecycle.py`
- Test: `tests/test_lifecycle.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_lifecycle.py`:

```python
from pathlib import Path

import pytest

from skill_rag import lifecycle


@pytest.fixture(autouse=True)
def no_mcp(monkeypatch):
    """Stub MCP edits — exercised separately in test_mcp_config."""
    monkeypatch.setattr(lifecycle.mcp_config, "unregister_claude", lambda **k: "noop")
    monkeypatch.setattr(lifecycle.mcp_config, "unregister_codex", lambda **k: False)
    monkeypatch.setattr(lifecycle.mcp_config, "register_claude", lambda *a, **k: "noop")
    monkeypatch.setattr(lifecycle.mcp_config, "register_codex", lambda *a, **k: False)


def _real_skill(root: Path, name: str) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\n---\nx\n")
    return d


def test_uninstall_removes_symlinks_keeps_real_dirs(tmp_path):
    corpus = tmp_path / "skills"
    corpus.mkdir()
    src = _real_skill(tmp_path / "src", "linked")
    (corpus / "linked").symlink_to(src, target_is_directory=True)
    _real_skill(corpus, "manual")          # hand-placed
    _real_skill(corpus, "using-skill-rag")  # bootstrap
    harness = tmp_path / "claude" / "skills"
    harness.mkdir(parents=True)
    (harness / "using-skill-rag").symlink_to(corpus / "using-skill-rag", target_is_directory=True)

    report = lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[harness])

    assert not (corpus / "linked").exists()             # symlink removed
    assert not (corpus / "using-skill-rag").exists()    # bootstrap removed
    assert (corpus / "manual").exists()                 # real dir kept
    assert not (harness / "using-skill-rag").exists()   # harness link removed
    assert report["corpus"]["removed_links"] == ["linked"]


def test_uninstall_purge_empties_corpus(tmp_path):
    corpus = tmp_path / "skills"
    _real_skill(corpus, "manual")
    _real_skill(corpus, "using-skill-rag")

    lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[], purge=True)

    assert list(corpus.iterdir()) == []


def test_uninstall_dry_run_changes_nothing(tmp_path):
    corpus = tmp_path / "skills"
    corpus.mkdir()
    src = _real_skill(tmp_path / "src", "linked")
    (corpus / "linked").symlink_to(src, target_is_directory=True)

    lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[], dry_run=True)

    assert (corpus / "linked").exists()


def test_uninstall_idempotent_on_empty(tmp_path):
    corpus = tmp_path / "skills"
    corpus.mkdir()
    lifecycle.uninstall(corpus_path=corpus, harness_skill_dirs=[])  # no error
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_lifecycle.py -q`
Expected: FAIL (`No module named 'skill_rag.lifecycle'`).

- [ ] **Step 3: Write the implementation**

Create `src/skill_rag/lifecycle.py`:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_lifecycle.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/skill_rag/lifecycle.py tests/test_lifecycle.py
git commit -m "feat(lifecycle): uninstall — corpus, index, harness links, MCP"
```

---

### Task 5: `lifecycle.install`

**Files:**
- Modify: `src/skill_rag/lifecycle.py`
- Test: `tests/test_lifecycle.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lifecycle.py`. This stubs `lifecycle.collect` and
`lifecycle.sync` so no embedding model is loaded:

```python
class _FakeCollect:
    def apply(self, **kwargs):
        return None


class _FakeSync:
    def run_sync(self):
        return {"added": [], "updated": [], "removed": [], "unchanged": 0}


def test_install_copies_bootstrap_and_links_harness(tmp_path, monkeypatch):
    corpus = tmp_path / "skills"
    harness = tmp_path / "claude" / "skills"
    monkeypatch.setattr(lifecycle, "collect", _FakeCollect(), raising=True)
    monkeypatch.setattr(lifecycle, "sync", _FakeSync(), raising=True)

    report = lifecycle.install(
        repo=tmp_path / "repo", corpus_path=corpus, harness_skill_dirs=[harness]
    )

    assert (corpus / "using-skill-rag" / "SKILL.md").exists()  # bootstrap copied
    assert (harness / "using-skill-rag").is_symlink()          # harness link
    assert report["bootstrap_installed"] is True
    assert report["collect_ran"] is True
    assert report["sync_ran"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_lifecycle.py::test_install_copies_bootstrap_and_links_harness -q`
Expected: FAIL (`module 'skill_rag.lifecycle' has no attribute 'install'`).

- [ ] **Step 3: Write the implementation**

In `src/skill_rag/lifecycle.py`, add `from . import collect` and `from . import sync` to the imports (so `lifecycle.collect` / `lifecycle.sync` are patchable), then add:

```python
def _copy_bootstrap(corpus_path: Path, dry_run: bool) -> bool:
    dest = corpus_path / corpus_mod.BOOTSTRAP_SKILL_NAME
    if dest.exists():
        return False
    if not dry_run:
        corpus_path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(BOOTSTRAP_SRC, dest)
    return True


def _link_bootstrap(harness_skill_dirs: list[Path], corpus_path: Path, dry_run: bool) -> list[str]:
    target = corpus_path / corpus_mod.BOOTSTRAP_SKILL_NAME
    linked: list[str] = []
    for d in harness_skill_dirs:
        link = d / corpus_mod.BOOTSTRAP_SKILL_NAME
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
) -> dict:
    repo = (repo or PROJECT_ROOT).expanduser()
    corpus_path = (corpus_path or corpus_mod.CORPUS_PATH).expanduser()
    harness_skill_dirs = (
        harness_skill_dirs if harness_skill_dirs is not None else default_harness_skill_dirs()
    )

    bootstrap_installed = _copy_bootstrap(corpus_path, dry_run)
    links = _link_bootstrap(harness_skill_dirs, corpus_path, dry_run)

    collect_ran = sync_ran = False
    mcp = {}
    if not dry_run:
        collect.apply(target=corpus_path)
        collect_ran = True
        sync.run_sync()
        sync_ran = True
        mcp["claude"] = mcp_config.register_claude(repo)
        mcp["codex"] = mcp_config.register_codex(repo)

    return {
        "bootstrap_installed": bootstrap_installed,
        "harness_links": links,
        "collect_ran": collect_ran,
        "sync_ran": sync_ran,
        "mcp": mcp,
        "dry_run": dry_run,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_lifecycle.py -q`
Expected: PASS (5 tests). The `no_mcp` fixture already stubs the register_* calls.

- [ ] **Step 5: Commit**

```bash
git add src/skill_rag/lifecycle.py tests/test_lifecycle.py
git commit -m "feat(lifecycle): install — bootstrap, harness links, collect, sync, MCP"
```

---

### Task 6: CLI — `install` / `uninstall` commands

**Files:**
- Modify: `src/skill_rag/cli.py` (imports near top; add commands after `reset`)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
from skill_rag import lifecycle as lifecycle_mod


def test_uninstall_command_dry_run(tmp_path, monkeypatch):
    runner = CliRunner()
    captured = {}
    def fake(**kwargs):
        captured.update(kwargs)
        return {"mcp": {}, "harness_links_removed": [], "index_dropped": False,
                "corpus": {"removed_links": [], "removed_dirs": [], "kept": []},
                "dry_run": True, "purge": False}
    monkeypatch.setattr(lifecycle_mod, "uninstall", fake)
    result = runner.invoke(app, ["uninstall", "--dry-run"])
    assert result.exit_code == 0
    assert captured["dry_run"] is True


def test_uninstall_command_confirm_decline_aborts(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(lifecycle_mod, "uninstall", lambda **k: pytest.fail("should not run"))
    result = runner.invoke(app, ["uninstall"], input="n\n")
    assert result.exit_code == 1


def test_install_command_invokes_lifecycle(tmp_path, monkeypatch):
    runner = CliRunner()
    called = {}
    monkeypatch.setattr(
        lifecycle_mod, "install",
        lambda **k: called.setdefault("ran", True) or {"bootstrap_installed": True,
            "harness_links": [], "collect_ran": True, "sync_ran": True, "mcp": {}, "dry_run": False},
    )
    result = runner.invoke(app, ["install"])
    assert result.exit_code == 0
    assert called["ran"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py -k "install or uninstall" -q`
Expected: FAIL (no such command: exit code 2).

- [ ] **Step 3: Write the implementation**

In `src/skill_rag/cli.py`, add `from . import lifecycle` to the imports block (lines 10-15). Add after the `reset` command (around line 140):

```python
@app.command()
def install(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show actions without writing."),
    json_out: bool = typer.Option(False, "--json"),
):
    """Install the bootstrap skill, collect+index skills, register the MCP server."""
    report = lifecycle.install(dry_run=dry_run)
    if json_out:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return
    typer.echo(f"bootstrap installed : {report['bootstrap_installed']}")
    typer.echo(f"harness links       : {len(report['harness_links'])}")
    typer.echo(f"collect ran         : {report['collect_ran']}")
    typer.echo(f"sync ran            : {report['sync_ran']}")
    typer.echo(f"mcp                 : {report['mcp']}")
    if dry_run:
        typer.echo("\n(dry-run — nothing written)")


@app.command()
def uninstall(
    purge: bool = typer.Option(False, "--purge", help="Also delete the entire ~/.skills corpus."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show actions without writing."),
    json_out: bool = typer.Option(False, "--json"),
):
    """Reverse `install`: unregister MCP, remove harness links + bootstrap + index.

    Default keeps hand-placed real skill dirs; `--purge` empties ~/.skills.
    """
    if not dry_run and not yes:
        scope = "the ENTIRE ~/.skills corpus" if purge else "skill-rag's footprint"
        typer.echo(f"About to remove {scope}, the index, harness links, and MCP registration.")
        if not typer.confirm("Continue?"):
            typer.echo("aborted.")
            raise typer.Exit(1)
    report = lifecycle.uninstall(purge=purge, dry_run=dry_run)
    if json_out:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
        return
    c = report["corpus"]
    typer.echo(f"mcp                 : {report['mcp']}")
    typer.echo(f"harness links removed: {len(report['harness_links_removed'])}")
    typer.echo(f"index dropped       : {report['index_dropped']}")
    typer.echo(f"corpus symlinks     : {len(c['removed_links'])}")
    typer.echo(f"corpus dirs removed : {len(c['removed_dirs'])}")
    typer.echo(f"corpus kept         : {len(c['kept'])}")
    if dry_run:
        typer.echo("\n(dry-run — nothing written)")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cli.py -q`
Expected: PASS (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/skill_rag/cli.py tests/test_cli.py
git commit -m "feat(cli): add install and uninstall commands"
```

---

### Task 7: `Makefile` + remove `scripts/install.sh`

**Files:**
- Create: `Makefile`
- Delete: `scripts/install.sh`

- [ ] **Step 1: Create the Makefile**

Create `Makefile` (recipes are tab-indented):

```makefile
.PHONY: install uninstall purge sync status reset eval test

install:
	uv sync
	SKILL_RAG_LOCAL_FILES_ONLY=0 uv run skill-rag install

uninstall:
	uv run skill-rag uninstall

purge:
	uv run skill-rag uninstall --purge

sync:
	uv run skill-rag sync

status:
	uv run skill-rag status

reset:
	uv run skill-rag reset

eval:
	uv run skill-rag eval

test:
	uv run pytest -q
```

- [ ] **Step 2: Verify Make targets parse**

Run: `make -n install uninstall purge`
Expected: prints the commands for each target without executing (exit 0).

- [ ] **Step 3: Remove the old script**

```bash
git rm scripts/install.sh
```

If `scripts/` is now empty, that's fine — git does not track empty dirs.

- [ ] **Step 4: Verify the full suite still passes**

Run: `uv run pytest -q`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add Makefile
git commit -m "feat: Makefile entry point; remove scripts/install.sh"
```

---

### Task 8: Update README (after implementation)

**Files:**
- Modify: `README.md` (Install §29-109, CLI table §127-138)
- Modify: `README.ko.md` (matching sections)

- [ ] **Step 1: Rewrite the English Install + CLI sections**

In `README.md`, replace the "## Install" section's one-shot setup and the MCP-registration prose with the Makefile flow, and remove the now-stale "Prints the MCP registration snippet" step (install now registers automatically):

```markdown
## Install

```bash
git clone <repo-url>
cd skill_rag
make install
```

`make install` is idempotent and does, in order:

1. `uv sync`
2. Installs the bootstrap meta-skill at `~/.skills/using-skill-rag/` and
   symlinks it into `~/.claude/skills/` and `~/.codex/skills/`
3. `skill-rag collect` — symlinks discovered harness skills into `~/.skills/`
4. `skill-rag sync` — downloads the embedding model on first run, builds the index
5. Registers the MCP server (Claude Code via `claude mcp add`; Codex via
   `~/.codex/config.toml`)

Restart the harness afterward.

## Uninstall

```bash
make uninstall   # removes skill-rag's footprint; keeps hand-placed skills
make purge       # also empties ~/.skills entirely
```

`uninstall` reverses install: unregisters the MCP server, removes the harness
bootstrap symlinks and the index, and removes collected symlinks + the bootstrap
skill. Hand-placed real skill directories under `~/.skills` are preserved unless
you use `purge`.
```

Add `install`, `uninstall`, `purge` rows to the CLI table (after `reset`):

```markdown
| `uv run skill-rag install` | Install bootstrap + collect/index + register MCP (use `make install`) |
| `uv run skill-rag uninstall [--purge] [--dry-run] [-y]` | Reverse install; `--purge` empties `~/.skills` |
```

- [ ] **Step 2: Mirror the changes in `README.ko.md`**

Apply the equivalent Korean edits: replace `bash scripts/install.sh` with
`make install`, add a `## 제거` section describing `make uninstall` / `make purge`,
and add the `install` / `uninstall` rows to the CLI table.

- [ ] **Step 3: Verify no stale references remain**

Run: `grep -rn "install.sh" README.md README.ko.md`
Expected: no matches (exit 1 from grep).

- [ ] **Step 4: Commit**

```bash
git add README.md README.ko.md
git commit -m "docs: document make install/uninstall lifecycle"
```

---

## Self-Review

**Spec coverage:**
- tomlkit dep + reference doc → Task 1 ✅
- `mcp_config.py` (Claude CLI-first + file fallback, Codex tomlkit) → Tasks 2-3 ✅
- `lifecycle.py` install/uninstall, idempotent, dry-run, purge, source preservation → Tasks 4-5 ✅
- CLI `install`/`uninstall` replacing `clean`, confirmation + `-y` + `--dry-run` → Task 6 ✅ (no `clean` exists at HEAD)
- Makefile + remove install.sh → Task 7 ✅
- README after implementation → Task 8 ✅
- eval recall@5 unaffected → full `pytest`/`eval` runs in Tasks 6-7 cover regression ✅

**Placeholder scan:** Task 5 Step 1 intentionally shows a first-draft test then a concrete replacement with an explicit "use ONLY the second version" instruction — no unresolved placeholders. No TBDs elsewhere.

**Type consistency:** `register_codex(repo, path=)`/`unregister_codex(path=)` return `bool`; `register_claude`/`unregister_claude` return `str` ('cli'|'file'|'noop'); `install`/`uninstall` return `dict` with the keys printed by the CLI in Task 6. `MCP_NAME`, `launch_args`, `BOOTSTRAP_SKILL_NAME` used consistently. Verified.
