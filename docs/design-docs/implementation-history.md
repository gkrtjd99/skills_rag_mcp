# Implementation History

This file consolidates completed dated specs and execution plans that used to
live under `docs/superpowers/`. Keep current behavior in `ARCHITECTURE.md`,
`docs/product-specs/skill-rag.md`, and the focused design docs. Use this file
only for historical context.

## 2026-05-28 - Centralized Skills + Lazy RAG Loading

The project moved from per-harness skill copies to a single user-global corpus
at `~/.skills/<name>/SKILL.md`. A bootstrap meta-skill became the only
always-loaded skill, and the MCP server exposed `search_skills` and `get_skill`
with explicit terminal statuses.

Important outcomes:

- Single corpus, single-user local design.
- TTL-based sync instead of filesystem watchers.
- LanceDB index keyed by `path`.
- Bootstrap skill excluded from retrieval.
- Loop-prevention contract for `ok`, `no_match`, and `not_found`.

Superseded details:

- Early plans used `all-MiniLM-L6-v2`, 384-dim vectors, schema v3, and a 0.35
  threshold. Current implementation uses bge-m3 by default, schema v5, hybrid
  retrieval, and a 0.45 dense threshold.
- Early install instructions referenced `scripts/install.sh`. Current setup is
  `make install` and `skill-rag install`.

## 2026-05-29 - Portable Eval Fixtures

The eval benchmark stopped depending on a user's private `~/.skills` corpus.
The repository now ships:

- `eval/fixtures/skills/`
- `eval/fixtures/queries.jsonl`

`skill-rag eval` defaults to those fixtures and a temporary LanceDB index. Users
can still evaluate their personal corpus with explicit `--corpus` and
`--dataset` paths.

## 2026-05-31 - Korean Search Recovery + Agent Tagging

Real-corpus checks showed English retrieval worked but Korean queries missed
many correct skills. The implemented recovery path added:

- Dense text normalization at Hangul/Latin boundaries.
- BM25 over full indexed text.
- Hangul character bigrams for Korean lexical matching.
- Reciprocal rank fusion of dense and sparse rankings.
- `agent` attribution from resolved skill paths.
- `search_skills(query, k=5, agent=None)` and hit-level `agent` metadata.

The original "native-skill exclusion" idea stayed out of scope. `agent` is
metadata only.

## 2026-06-02 - Install / Uninstall Lifecycle

The one-way install script was replaced with a testable lifecycle:

- `Makefile` wraps `uv run skill-rag ...`.
- `skill-rag install` copies the bootstrap when missing, links harnesses,
  collects skills, syncs the index, and registers MCP.
- `skill-rag uninstall` unregisters MCP, removes harness bootstrap symlinks,
  drops the index, and removes collected symlinks plus the bootstrap.
- `skill-rag uninstall --purge` empties `~/.skills`.
- Claude Code registration prefers `claude mcp add/remove`; Codex registration
  edits `~/.codex/config.toml` with tomlkit.

## 2026-06-02 - Multilingual Description Translation

To improve cross-language retrieval for monolingual upstream skills,
index-time local ko<->en description translation was added:

- `translate.py` detects Korean vs English with a script-count heuristic.
- MarianMT models (`Helsinki-NLP/opus-mt-ko-en`,
  `Helsinki-NLP/opus-mt-en-ko`) run locally.
- Only the description is translated.
- Translated text is folded into `SkillRecord.embed_text()`, affecting both
  dense vectors and BM25 text.
- Added/changed records are translated during sync. Unchanged records are not
  retranslated.
- `SKILL_RAG_TRANSLATE=0` disables the feature.

No schema column was added for the translation itself. Existing indexes need
`skill-rag reset && skill-rag sync` when `embed_text()` content semantics
change.

## 2026-06-02 - Offline Runtime Enforcement

An eval run exposed Hugging Face metadata HTTP requests even with
`SKILL_RAG_LOCAL_FILES_ONLY=1`. The fix added a shared helper that sets
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` before lazy embedding or
translation model imports. Setup remains explicit: `make install` sets
`SKILL_RAG_LOCAL_FILES_ONLY=0` when first-time model downloads are intended.
