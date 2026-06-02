# Install / uninstall lifecycle via Makefile + CLI

Date: 2026-06-02
Status: approved

## Problem

The repo can be *installed* (`scripts/install.sh`) but not cleanly *uninstalled*.
There is no command that reverses install: it leaves behind the corpus symlinks,
the copied bootstrap meta-skill, the harness bootstrap symlinks, the LanceDB
index, and the MCP-server registration in `~/.claude.json` / `~/.codex/config.toml`.

A `clean` CLI command was added earlier in this session but is inadequate and
misleading: it only touches the corpus + index, never the harness links or MCP
registration, and its help implied `collect && sync` could fully restore what it
removed. That is false for this environment — most `~/.skills` entries are
symlinks into sources (`~/.skills-src/`, `_skills/agent-skills/skills/`) that
`collect` does not scan, so they cannot be auto-restored. See
`memory/skills-corpus-layout.md`.

The goal is a clean, symmetric install/uninstall lifecycle so the repo can be
set up and torn down reliably — supporting the broader aim of putting many
skills behind RAG to raise agent quality while lowering token use.

## Decisions

- **Control surface: a `Makefile`**, not shell scripts. `scripts/install.sh` is
  **removed**; its logic moves into a Python CLI command.
- **Logic lives in the Python CLI** (testable), Makefile targets are thin
  wrappers over `uv run skill-rag ...`.
- The earlier `clean` CLI command is **replaced** by `uninstall`.
- **MCP registration: official CLI first.** Claude Code via `claude mcp
  add/remove`; only fall back to editing `~/.claude.json` when `claude` is not on
  PATH. Codex has no such CLI, so edit `~/.codex/config.toml` directly.
- **Add `tomlkit` dependency** for format-preserving TOML edits (recorded in
  `pyproject.toml` + `docs/references/`).
- **Corpus removal default = skill-rag's own footprint only** (collected
  symlinks + the bootstrap dir). Hand-placed real skill directories,
  `~/.skills-src`, and `_skills` are never touched. `--purge` removes all of
  `~/.skills`.
- README is updated **after** implementation to match the shipped commands.

## Changes

### 1. New module `src/skill_rag/mcp_config.py`
Harness-agnostic registration helpers, all paths injectable for testing:
- `register_claude(repo)` / `unregister_claude()` — prefer `claude mcp
  add/remove skill-rag --scope user`; fall back to editing the `mcpServers`
  object in `~/.claude.json` (back up first; atomic temp-file + rename).
- `register_codex(repo)` / `unregister_codex()` — add/remove the
  `[mcp_servers.skill-rag]` block in `~/.codex/config.toml` via `tomlkit`
  (preserve other content; atomic write).
- Each operation is idempotent: registering an existing entry is a no-op;
  unregistering an absent entry is a no-op. Missing harness/config files are
  skipped gracefully.

### 2. New module `src/skill_rag/lifecycle.py`
Orchestrates the full sequence, returning a structured report:
- `install(repo)` — (1) copy `bootstrap-skill/using-skill-rag` →
  `~/.skills/using-skill-rag`; (2) symlink the bootstrap into
  `~/.claude/skills` and `~/.codex/skills`; (3) `collect`; (4) `sync` (first run
  forces model download); (5) register MCP for each detected harness.
- `uninstall(purge=False)` — exact reverse: (1) unregister MCP; (2) remove
  harness bootstrap symlinks; (3) drop the index (`index.reset` +
  `sync.reset_cache`); (4) corpus cleanup — default removes collected symlinks +
  the bootstrap dir, `purge=True` removes all of `~/.skills`.
- Both idempotent (re-running is safe, exit 0 when nothing to do).
- Corpus cleanup reuses the symlink-vs-real distinction already in
  `collect.clean` (folded into lifecycle): symlinks are unlinked; the bootstrap
  dir is removed; other real dirs are preserved unless `purge`.

### 3. CLI changes (`cli.py`)
- Remove the `clean` command and `collect.clean` / `CleanReport` (superseded).
- Add `install` — `--dry-run`, `--json`.
- Add `uninstall` — `--purge`, `--dry-run`, `--yes/-y` (destructive →
  confirmation prompt unless `-y`), `--json`.
- `reset`, `sync`, `status`, `query`, `list-skills`, `collect`, `eval`, `mcp`
  are unchanged.

### 4. `Makefile` (new) + remove `scripts/install.sh`
Thin targets:
- `install`  → `uv sync && uv run skill-rag install`
- `uninstall`→ `uv run skill-rag uninstall`
- `purge`    → `uv run skill-rag uninstall --purge`
- convenience: `sync`, `status`, `reset`, `eval`, `test`
Delete `scripts/install.sh` (and `scripts/` if it becomes empty).

### 5. Docs
- `pyproject.toml`: add `tomlkit`; `docs/references/tomlkit-llms.txt`: add a
  quick reference (per AGENTS.md dependency rule).
- README.md / README.ko.md: rewrite the Install + CLI sections around
  `make install` / `make uninstall` / `make purge` — **done after
  implementation**, matching the shipped surface.

## Verification

- All steps TDD (red → green).
- `test_mcp_config.py`: register→unregister round-trip preserves unrelated
  config entries; absent-entry unregister is a no-op; `claude`-missing falls back
  to JSON edit.
- `test_lifecycle.py`: install→uninstall round-trip leaves no footprint;
  `--purge` empties the corpus; hand-placed real dirs survive a non-purge
  uninstall; dry-run writes nothing; idempotent re-runs.
- `test_cli.py`: drop `clean` tests; add `install` / `uninstall` (incl.
  confirmation-decline aborts with exit 1, `-y` skips prompt).
- `uv run skill-rag eval` recall@5 ≥ 0.8 — unaffected, confirm no regression.
- Manual: `make install` then `make uninstall` on the real machine; verify
  `~/.skills`, harness links, index, and both MCP configs return to a clean
  state, and that `~/.skills-src` / `_skills` are untouched.

## Out of scope

- Search/retrieval quality changes (already handled; bge-m3 + hybrid).
- Restoring or migrating `~/.skills-src` sources.
- A `skill-rag collect`-side stale-symlink cleaner.
- MCP registration for harnesses other than Claude Code and Codex.
