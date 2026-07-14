# Architecture

skill_rag serves a single user-global skill corpus
(`~/.skills/<name>/SKILL.md`) to AI agents via an MCP server. The skill-rag
path starts with one bootstrap meta-skill in context and lazily fetches other
skill bodies only when retrieval says they apply. A harness's independent
native skill loader may still run; skill-rag does not disable that fallback.

## Module Boundaries

```
src/skill_rag/
├── agents.py       # infer source harness from filesystem paths
├── corpus.py       # corpus path, thresholds, TTL constants
├── models.py       # SkillRecord, SearchHit
├── parser.py       # SKILL.md text -> SkillRecord
├── loader.py       # ~/.skills/ -> [SkillRecord]
├── normalize.py    # dense-query/text normalization
├── offline.py      # enforce local-only Hugging Face runtime mode
├── embed.py        # sentence-transformers wrapper (L2-normalized)
├── translate.py    # local ko<->en description translation
├── sparse.py       # in-memory BM25 + Korean-aware tokenization
├── index.py        # LanceDB CRUD (schema v6)
├── retrieve.py     # hybrid search + threshold/status response
├── sync.py         # disk<->index diff; TTL cache (only stateful module)
├── mcp_server.py   # FastMCP tools: search_skills, get_skill
├── collect.py      # symlink harness skills into ~/.skills/
├── mcp_config.py   # Claude/Codex MCP registration helpers
├── lifecycle.py    # install/uninstall orchestration
├── cli.py          # Typer CLI
└── evaluator.py    # recall@k, MRR, latency

bench/              # disposable Docker model matrix benchmark and reports
```

Each module owns one responsibility. `sync` is the only module with mutable
runtime state (a single timestamp).

## Request Flow

### `search_skills(query, k, agent)`

0. `retrieve.is_conversational(query)` runs first. A bare interactive-flow reply
   (single letter, all digits, or a curated ko/en affirmation/ack token) returns
   `{status: "skip"}` immediately — no sync, no embedding, no search.
1. `sync.sync_if_stale()` runs at most once per TTL window (default 30 s).
2. `retrieve.search` reads indexed metadata and text.
3. The query is normalized for dense retrieval, then encoded with the local
   embedding model (`intfloat/multilingual-e5-base` by default).
4. LanceDB returns dense cosine scores over the indexed vectors.
5. BM25 scores are computed in memory over the indexed `text` column. The
   tokenizer preserves Latin/code tokens and emits Hangul character bigrams.
6. A candidate is kept when dense cosine clears `SCORE_THRESHOLD` (default
   0.45) or normalized BM25 clears `BM25_THRESHOLD` (default 0.30).
7. Kept candidates are ordered by reciprocal rank fusion (`RRF_K`, default 60).
8. Returns `{status: "ok", hits}` or `{status: "no_match", hits: [], message}`.

Hits contain `{name, description, score, agent}`. The caller-supplied `agent`
argument is informational today; each hit reports the source harness inferred
from the skill path.

### `get_skill(name)`

1. Look up the indexed row whose frontmatter `name` matches `name`.
2. Read that row's `path` directly. This avoids assuming directory name equals
   frontmatter name.
3. On miss or stale path, force `sync_if_stale(ttl=0)` and retry once.
4. Return `{status: "ok", body}` or `{status: "not_found", message}`.

## Sync

- `loader.scan(~/.skills)` returns one `SkillRecord` per direct
  `<name>/SKILL.md` directory. `sync.run_sync()` accepts an internal corpus-path
  override for lifecycle/test isolation; runtime calls use `~/.skills`.
- Sync and TTL checks are serialized by an in-process reentrant lock so two
  MCP calls cannot mutate the same derived index concurrently.
- `using-skill-rag` is skipped because the bootstrap skill is already loaded by
  the harness.
- `agent` is inferred from the resolved path (`.claude`, `.codex`,
  `.antigravity`, or `local`).
- Diffing is by `path` and `content_hash`.
- Added/changed records get description translation at index time
  (`translate.translate_for_index`) before upsert.
- Unchanged rows whose prior `translation_status` is `failed`, `disabled`, or
  `pending` are retried when translation is enabled.
- Removed paths are deleted from LanceDB.

## Data Schema

LanceDB table `skills` (schema v6):

| Column | Type | Notes |
| --- | --- | --- |
| `path` | string | Primary key for `merge_insert`; points to `SKILL.md`. |
| `name` | string | Frontmatter skill name. |
| `description` | string | Frontmatter description. |
| `content_hash` | string | sha256 of the full `SKILL.md`. |
| `text` | string | `name`, `description`, translated description, and body. |
| `agent` | string | Source harness: `claude-code`, `codex`, `antigravity`, `local`, etc. |
| `translation_status` | string | `ok`, `failed`, `disabled`, `skipped`, or `pending`. |
| `vector` | list<float32>[dim] | Embedding of `text`; `dim` comes from the selected model. |

Any Arrow schema drift (including a vector dimension change) drops and
recreates the table because the index is a derived cache. Content-only changes
to `embed_text()` still require `skill-rag reset`
followed by `skill-rag sync`.

## Install Lifecycle

`make install` runs `uv sync` and then `SKILL_RAG_LOCAL_FILES_ONLY=0 uv run
skill-rag install`. The CLI command:

1. Copies the bootstrap template into `~/.skills/using-skill-rag/` if missing.
2. Symlinks that installed bootstrap into Claude Code and Codex skill dirs.
3. Collects discovered harness skills into `~/.skills/` as symlinks.
4. Runs sync, downloading local models during first setup when needed.
5. Registers the MCP server for Claude Code and Codex.

`skill-rag uninstall` reverses this. Non-purge uninstall removes skill-rag's
recorded footprint and collected symlinks but preserves untracked user entries
under `~/.skills`. Installation ownership is recorded locally in
`~/.skills/.skill-rag-install-state.json`.

## Loop Prevention

The bootstrap skill and server response shapes jointly prevent retry loops:

| Tool | Failure shape | Response status | Bootstrap rule |
| --- | --- | --- | --- |
| `search_skills` | Bare interactive-flow reply (single letter, digits, ko/en ack) | `skip` | Respond directly. Stop searching every turn until a new task. |
| `search_skills` | Empty query, empty corpus, or no candidate above thresholds | `no_match` | Respond directly. No reworded retry. |
| `get_skill` | Missing skill after forced sync | `not_found` | Do not retry this name this turn. |
| `search_skills` | Hits returned, none actually fit | `ok` (agent judges) | Proceed without a skill. |

## Constraints

- Local-first: no cloud APIs at index or query time.
- Python 3.13 + uv. No `pip` or raw `venv`.
- Single user, single corpus.
- `~/.skills/` is user-managed and never committed.
- Model loading defaults to local cache only. `make install` explicitly sets
  `SKILL_RAG_LOCAL_FILES_ONLY=0` for first-time local model setup.
