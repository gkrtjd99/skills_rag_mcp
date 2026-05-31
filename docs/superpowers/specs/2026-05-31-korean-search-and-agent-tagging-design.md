# Korean search recovery + agent-source tagging

Date: 2026-05-31
Status: approved (builds on the pushed hybrid-retrieval commit `a47b58f`)

## Problem

skill-rag collects skills from multiple agents (codex, claude code,
antigravity, …) into `~/.skills/` via symlink and exposes them through one RAG
MCP. The symlink → index → `get_skill` path works. Retrieval works **in
English**. It fails in **Korean**: against the real 76-skill corpus, 0 of 7
representative Korean queries returned the correct skill.

### Measured root causes (real corpus)

1. **No Korean tokenization (BM25 dead in Korean).** `tokenize` splits on
   whitespace/`\w+`, so Korean particles glue to words:
   - `tokenize('vercel에 배포')` → `['vercel에', '배포']` — the corpus token is
     `vercel`, never `vercel에`.
   - BM25 top score: `'vercel deploy'` = 5.01 ✅ vs `'vercel에 배포'` = 0.00 ❌,
     `'코드리뷰 받고 싶어'` = 0.00 ❌.

2. **Dense cosine too low in Korean.** Same meaning, different score:
   - `'review code'` → `requesting-code-review` = 0.585 ✅
   - `'코드 리뷰 해줘'` → correct skill absent from top-3, best 0.233
   - `'코드리뷰 받고 싶어'` → top-1 `cardputer-buddy` = 0.157 (wrong)
   - Signal: `'코드 리뷰'` (spaced) = 0.233 > `'코드리뷰'` (glued) = 0.157.
     Normalization/segmentation is the lever.

`get_skill`, symlinking, and indexing are NOT the problem and are unchanged.

## Decisions

- Korean handling: **dependency-free, lightweight** (no kiwipiepy, no model swap).
- Agent identity: **caller passes it** via `search_skills(query, agent=...)`;
  the meta-skill instructs each harness to send its own name.
- Native-skill exclusion filter: **out of scope** for now (tag + display only).
- History: **stack on top** of the pushed commit; no rewrite.

## Changes

### 1. Korean tokenizer (sparse.py) — fixes cause #1
Replace `tokenize` with dual tokenization:
- keep word tokens (preserve English / code identifiers: `vercel`, `worktree`);
- additionally emit Korean **char 2-grams** for each Hangul run:
  `코드리뷰` → `코드`, `드리`, `리뷰`, …
- a Hangul run glued to latin (`vercel에`) yields the latin word token `vercel`
  PLUS the Hangul n-grams of `에`.
Query and corpus use the same function, so `vercel에 배포` again produces the
`vercel` token (BM25 > 0) and `코드리뷰` matches via `리뷰` partial overlap.

### 2. Dense query/corpus normalization (retrieve.py + models.py) — eases cause #2
Insert a space at every Hangul↔Latin boundary before encoding
(`vercel에` → `vercel 에`). Apply the SAME normalization to the embedded text
(`SkillRecord.embed_text`) so query and document are encoded consistently.
Requires a one-time reindex (content_hash already covers embed-text changes via
file hash; reindex is forced by `reset` + `sync`).

### 3. Agent-source tagging (index.py, collect.py, mcp_server.py, retrieve.py)
- index schema v5: add `agent` column (auto-migrate, like v4 → rebuild).
- `collect` records the source harness when linking (derive from the source
  path: `.claude` → `claude-code`, `.codex` → `codex`, else `unknown`).
- `SkillRecord` gains an `agent` field; loader infers it from the resolved
  symlink target of the skill dir.
- `search_skills(query, k=5, agent=None)` — new optional param; the `agent`
  value is currently informational. Each hit includes its `agent`.
- meta-skill `using-skill-rag`: instruct the caller to pass its harness name.

### 4. Eval recalibration (eval/fixtures, corpus.py)
- Re-measure threshold + any n-gram weighting against the Korean fixtures
  already added, plus confirm no English regression.

## Verification
- All steps TDD (red → green).
- After implementation: `reset` + `sync` the real corpus, then re-run the 7
  Korean queries that previously scored 0/7 and report hit counts as clean JSON.
- `uv run skill-rag eval` recall@5 must not regress on English cases.

## Out of scope
Recovering the 5 deleted vercel skills, native-skill exclusion filter,
embedding-model swap, collect stale-link cleanup.
