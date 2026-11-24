# skill_rag

[한국어](README.md) | **English**

A local RAG that searches the skills collected under `~/.skills/` in natural
language and loads only the relevant ones into the agent's context.

skill-rag auto-loads only one meta-skill at session start; the remaining N
skills are searched per new task via MCP, and only matching bodies are fetched.
The native skill-loader settings of Claude/Codex are independent and remain
available as a fallback.

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

- Embeddings: `intfloat/multilingual-e5-base` running locally with the model's
  `query:`/`passage:` prompts (no external API calls). Strong cross-lingual
  retrieval — Korean queries match English skill descriptions.
- Retrieval keeps the LanceDB metadata and BM25 structure hot between MCP
  calls, and uses a small local Korean intent bridge. Warm searches stay below
  the one-second target on a roughly 50-skill corpus.
- Search returns metadata only, with hit descriptions capped at 280 characters;
  `get_skill` is the explicit path for the full body.
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
4. `skill-rag sync` — downloads the embedding model on first run and builds the index. Local description translation is optional and disabled by default.
5. Registers the MCP server (Claude Code via `claude mcp add`; Codex via
   `~/.codex/config.toml`)

Restart the harness afterward.

> Upgrading from the previous unprompted E5 index? Schema metadata detects the
> stale embedding profile and rebuilds it on the next sync. You can also run
> `uv run skill-rag reset && uv run skill-rag sync` explicitly. Set
> `SKILL_RAG_TRANSLATE=1` only when local ko↔en description augmentation is
> needed; it adds an index-time translation model and cost.

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
| `make eval-natural` | Evaluate the bilingual natural-language fixture at top-1 |
| `make eval-no-match` | Evaluate no-match accuracy on unrelated queries |
| `make eval-codex` | Evaluate the five Codex system skills with the fixed gold set |
| `make eval-personal` | Evaluate a personal corpus with its matching gold set (`SKILL_RAG_EVAL_CORPUS`, `SKILL_RAG_EVAL_DATASET`) |
| `uv run skill-rag reset` | Reset the index |
| `uv run skill-rag mcp` | Run the MCP server |
| `uv run skill-rag install [--refresh-bootstrap]` | Install bootstrap + collect/index + register MCP (use `make install`). `--refresh-bootstrap` overwrites the existing meta-skill from the template |
| `uv run skill-rag uninstall [--purge] [--dry-run] [-y]` | Reverse install; `--purge` empties `~/.skills` |

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `SKILL_RAG_CORPUS_PATH` | `~/.skills` | Corpus path |
| `SKILL_RAG_INDEX_PATH` | `./var/index.lance` | LanceDB path |
| `SKILL_RAG_MODEL` | `intfloat/multilingual-e5-base` | Embedding model |
| `SKILL_RAG_LOCAL_FILES_ONLY` | `1` | Load embedding and translation models from local cache only |
| `SKILL_RAG_MAX_SEQ_LENGTH` | `64` | Embedding input token cap |
| `SKILL_RAG_DENSE_BODY_CHARS` | `0` | Optional opening-body characters added to dense passages (BM25 keeps the full body) |
| `SKILL_RAG_SCORE_THRESHOLD` | `0.78` | Dense match threshold calibrated against positive and negative fixtures |
| `SKILL_RAG_DENSE_ONLY_THRESHOLD` | `0.86` | Higher confidence required when a dense hit has no meaningful lexical evidence |
| `SKILL_RAG_DENSE_ONLY_MARGIN_THRESHOLD` | `0.05` | Top-vs-runner-up cosine gap accepted for a strong small-corpus dense match |
| `SKILL_RAG_BM25_THRESHOLD` | `0.30` | Normalized BM25 threshold |
| `SKILL_RAG_BM25_MIN_QUERY_COVERAGE` | `0.50` | Meaningful query-term coverage required for lexical rescue |
| `SKILL_RAG_RRF_K` | `60` | Dense/BM25 reciprocal-rank-fusion constant |
| `SKILL_RAG_DENSE_CANDIDATE_MULTIPLIER` | `4` | Dense shortlist multiplier relative to requested `k` |
| `SKILL_RAG_MIN_DENSE_CANDIDATES` | `20` | Minimum dense shortlist size |
| `SKILL_RAG_MAX_HIT_DESCRIPTION_CHARS` | `280` | MCP metadata description cap (`0` disables the cap) |
| `SKILL_RAG_TRANSLATE` | `0` | Optional local description translation at index time (`1` enables) |
| `SKILL_RAG_SYNC_TTL` | `30` | Sync cache TTL (seconds) |
| `SKILL_RAG_RERANK` | (off) | Second-stage fit judge: `jev`, `openai`, or your own `package.module:factory` (cloud call, see below) |
| `SKILL_RAG_RERANK_CANDIDATES` | `16` | Candidate skills shown to the judge |
| `SKILL_RAG_RERANK_THRESHOLD` | `0.5` | Minimum fit probability for a skill to be returned |
| `SKILL_RAG_RERANK_MODEL` | (provider default) | Pin the judge model id (for example `jev-1.14.0`, `gpt-6-luna`) |
| `SKILL_RAG_RERANK_TIMEOUT` | `5` | Judge request timeout (seconds) |
| `SKILL_RAG_RERANK_COOLDOWN` | `60` | Seconds to stay on the local gate after a failed judge call |
| `SKILL_RAG_RERANK_DESCRIPTION_CHARS` | `120` | Description cap for judged hits (`0` disables the cap) |

### Optional: judge rerank (off by default)

The default thresholds are calibrated on the public fixture and can lose
accuracy on other corpora. When enabled, local hybrid search only proposes
candidates and a judge model returns, per candidate, the probability that it
fits the query. Measured on a held-out corpus of 45 skills and 133 queries:

| | Default gate | `jev` | `openai` |
| --- | ---: | ---: | ---: |
| recall@1 | 0.726 | 0.979 | 0.968 |
| no-match accuracy | 0.395 | 1.000 | 0.947 |
| Search response size (mean characters) | 1,184 | 237 | 230 |
| Latency p50 | 31 ms | 211 ms | 496 ms |
| Input tokens per request | none | 4,411 | 6,013 |

Method and limits: `docs/benchmarks/2026-11-24-heldout-jev-rerank.md`.

```bash
# TypeSafe Jev
uv sync --extra rerank
export TYPESAFE_API_KEY=...
export SKILL_RAG_RERANK=jev

# or the OpenAI Decisions API (no extra package)
export OPENAI_API_KEY=...
export SKILL_RAG_RERANK=openai
```

- When on, every search sends **the query text and the candidate skills'
  names and descriptions** to the chosen provider's API. Skill bodies and
  paths are not sent. When off, nothing leaves the machine.
- Input tokens are billed.
- Any failure (SDK missing, no key, no credits, timeout) returns the local
  gate's result.
- To plug in another model, implement `skill_rag.judges.Judge` (methods
  `fits` and `unavailable_reason`) and set
  `SKILL_RAG_RERANK=your_package.module:factory`.
- Check the `rerank` line of `uv run skill-rag status`.

`skill-rag eval` defaults to repository-owned fixtures under `eval/fixtures/`
so GitHub users get the same benchmark. The Codex system-skill gold set targets
`~/.codex/skills/.system` on the current machine:

```bash
make eval-codex
```

For an arbitrary personal corpus, create a matching gold set using skill names
that actually exist in that corpus and provide both paths:

```bash
SKILL_RAG_EVAL_CORPUS=~/.skills \
SKILL_RAG_EVAL_DATASET=eval/my-corpus-queries.jsonl \
make eval-personal
```

Use `make benchmark-docker` for the model matrix, or
`make benchmark-natural-docker` for the stricter bilingual natural-language
comparison.

## Docs

- `AGENTS.md` — reading order before an agent's first task
- `ARCHITECTURE.md` — module structure
- `docs/product-specs/skill-rag.md` — what and why
- `docs/design-docs/` — design decision log
- `docs/design-docs/implementation-history.md` — completed historical specs/plans
- `docs/superpowers/` — active feature specs/plans, when present
