# skill_rag

[한국어](README.md) | **English**

A local RAG that searches the skills collected under `~/.skills/` in natural
language and loads only the relevant ones into the agent's context.

At session start only a single meta-skill is auto-loaded; the remaining N
skills are searched per user message via MCP, and only the matching bodies
are fetched. This avoids burning context by reading every skill up front.

## How it works

```
user message
   │
   ▼
agent → search_skills(query)  ─→ top-k metadata (name, desc, score)
                                       │
                                       ▼ only the relevant ones
                                  get_skill(name) ─→ SKILL.md body
```

- Embeddings: `BAAI/bge-m3` running locally (no external API calls). Strong
  cross-lingual retrieval — Korean queries match English skill descriptions.
- Vector DB: LanceDB
- Index: auto-synced with a 30s TTL cache on each `search_skills` call

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
4. `skill-rag sync` — downloads the embedding and translation models on first run, builds the index
5. Registers the MCP server (Claude Code via `claude mcp add`; Codex via
   `~/.codex/config.toml`)

Restart the harness afterward.

> Upgrading from a version before ko↔en translation? Run
> `uv run skill-rag reset && uv run skill-rag sync` once to rebuild the index
> with translations (the schema is unchanged, so it won't auto-rebuild).

### Sanity check

After restarting the harness, in a fresh session:

- Confirm the `using-skill-rag` meta-skill auto-loads at start
- Confirm the `mcp__skill-rag__search_skills` tool is visible in any message
- Try it directly: `search_skills(query="...", k=5)` → `{status: "ok"|"no_match", hits, ...}`

You can also verify the same search from the CLI:

```bash
uv run skill-rag query "deploy to vercel"
```

### Other MCP-compatible clients (Cursor, Windsurf, etc.)

`make install` auto-registers Claude Code and Codex only. For other clients,
register the MCP server manually using:

```
uv --directory <repo> run skill-rag mcp
```

## Uninstall

```bash
make uninstall   # removes skill-rag's footprint; keeps hand-placed skills
make purge       # also empties ~/.skills entirely
```

`uninstall` reverses install: unregisters the MCP server, removes the harness
bootstrap symlinks and the index, and removes collected symlinks + the bootstrap
skill. Hand-placed real skill directories under `~/.skills` are preserved unless
you use `purge`.

## Adding a skill

Write a file at `~/.skills/<name>/SKILL.md`:

```markdown
---
name: my-skill
description: One-line description. Search accuracy depends on this.
---

# Body
Detailed usage of the skill.
```

It is auto-indexed within 30s on the next `search_skills` call.

## CLI

| Command | Description |
| --- | --- |
| `uv run skill-rag status` | Show corpus path, model, index size, threshold |
| `uv run skill-rag collect [--dry-run]` | Symlink harness skills into `~/.skills/` |
| `uv run skill-rag sync` | Manually sync the index |
| `uv run skill-rag query "<text>"` | Inspect search results |
| `uv run skill-rag list-skills` | List indexed skills |
| `uv run skill-rag eval` | Measure recall@5 against the public fixture eval |
| `uv run skill-rag reset` | Reset the index |
| `uv run skill-rag mcp` | Run the MCP server |
| `uv run skill-rag install` | Install bootstrap + collect/index + register MCP (use `make install`) |
| `uv run skill-rag uninstall [--purge] [--dry-run] [-y]` | Reverse install; `--purge` empties `~/.skills` |

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `SKILL_RAG_CORPUS_PATH` | `~/.skills` | Corpus path |
| `SKILL_RAG_INDEX_PATH` | `./var/index.lance` | LanceDB path |
| `SKILL_RAG_MODEL` | `BAAI/bge-m3` | Embedding model |
| `SKILL_RAG_LOCAL_FILES_ONLY` | `1` | Load embedding and translation models from local cache only |
| `SKILL_RAG_MAX_SEQ_LENGTH` | `512` | Embedding input token cap |
| `SKILL_RAG_SCORE_THRESHOLD` | `0.45` | Dense match threshold (calibrated for bge-m3) |
| `SKILL_RAG_BM25_THRESHOLD` | `0.30` | Normalized BM25 threshold |
| `SKILL_RAG_RRF_K` | `60` | Dense/BM25 reciprocal-rank-fusion constant |
| `SKILL_RAG_TRANSLATE` | `1` | Auto-translate each description ko↔en at index time (`0` disables) |
| `SKILL_RAG_SYNC_TTL` | `30` | Sync cache TTL (seconds) |

`skill-rag eval` defaults to repository-owned fixtures under `eval/fixtures/`
so GitHub users get the same benchmark. To inspect your personal corpus, pass
both paths explicitly:

```bash
uv run skill-rag eval --corpus ~/.skills --dataset eval/queries.jsonl
```

## Docs

- `AGENTS.md` — reading order before an agent's first task
- `ARCHITECTURE.md` — module structure
- `docs/product-specs/skill-rag.md` — what and why
- `docs/design-docs/` — design decision log
- `docs/design-docs/implementation-history.md` — completed historical specs/plans
- `docs/superpowers/` — active feature specs/plans, when present
