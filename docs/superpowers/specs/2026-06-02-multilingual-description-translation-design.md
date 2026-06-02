# Multilingual description auto-translation

Date: 2026-06-02
Status: approved

## Problem

A skill's `description` is written in a single language (English for most
GitHub/plugin skills, Korean for the user's `k-skill` set). `bge-m3` dense
retrieval is cross-lingual, so a Korean query against an English-only skill
still scores — but ~0.5–0.6, often below the 0.45 threshold's comfortable
margin, and BM25 (lexical) never matches across languages at all. Result:
a skill whose behavior fits the query is **not retrieved** purely because the
query language differs from the description language, so the agent never loads
it.

The user is about to add many third-party skills pulled from GitHub, all
monolingual. Hand-editing each `SKILL.md` is impractical: the corpus entries
are symlinks to upstream sources that get overwritten on update.

## Decisions

- **Index-time auto-translation** (not author-provided fields). Upstream/GitHub
  skills can't carry curated bilingual fields, so translation must be automatic.
  (Forward-compatible: a future "skip if a bilingual field already exists"
  branch can add the author-provided path without a rewrite.)
- **Korean ↔ English only.** `Helsinki-NLP/opus-mt-ko-en` + `opus-mt-en-ko`
  (small, good ko-en quality). No general multilingual MT model.
- **Translate the `description` only** — the high-signal one-liner. The body is
  long and noisy; excluded.
- **Cache = content-hash based.** Translate only added/changed records at sync;
  unchanged skills are never re-translated. No extra stored column.
- **Local-only.** Runs entirely on a local MT model — no cloud calls
  (consistent with `core-beliefs.md`).
- **Toggle.** `SKILL_RAG_TRANSLATE` (default `1`); `0` disables.

## Changes

### 1. New module `src/skill_rag/translate.py`
- `detect_lang(text) -> "ko" | "en"`: Hangul-ratio heuristic (dependency-free).
- `translate(text) -> str`: `ko` → `opus-mt-ko-en`, `en` → `opus-mt-en-ko`;
  one pass. Models lazy-loaded per direction and cached in a module global.
  Honors `SKILL_RAG_LOCAL_FILES_ONLY`. Returns `""` on empty input, model-load
  failure, or any error (graceful — indexing continues without the translation).
- Model name constants overridable via env (`SKILL_RAG_MT_KO_EN`,
  `SKILL_RAG_MT_EN_KO`).

### 2. `models.SkillRecord` (models.py)
- Add field `description_translated: str = ""`.
- `embed_text()` appends `description_translated` (after name/description/body)
  when non-empty, then `normalize_for_dense`. So the translation lands in BOTH
  the dense vector and the BM25 `text` with no schema change.

### 3. Sync wiring (sync.py)
- In `run_sync`, after computing `to_upsert` (the added/changed records), fill
  each record's `description_translated` via `translate.translate(...)` when
  `SKILL_RAG_TRANSLATE` is on. Unchanged records are not in `to_upsert`, so they
  are never re-translated. Then `index.upsert(to_upsert)` as today.

### 4. Index (index.py)
- **No schema change.** `text` = `embed_text()` already, so it now carries the
  translation; the vector is encoded from the same text. Bump the schema-version
  comment to note the `text`/vector CONTENT change and that a one-time
  `reset && sync` rebuild is required for pre-existing indexes (not a column
  migration). The current corpus is empty, so no live migration is needed.

### 5. Config / dependencies
- `SKILL_RAG_TRANSLATE` (default `1`) in `corpus.py`.
- Add `sentencepiece` and `sacremoses` (MarianMT tokenizer needs them);
  `transformers` is already present via `sentence-transformers`. Record both in
  `pyproject.toml` and `docs/references/` per the AGENTS dependency rule.
- The MT models download during `make install`'s first sync
  (`SKILL_RAG_LOCAL_FILES_ONLY=0`), alongside `bge-m3`.

## Verification

- All steps TDD (red → green).
- `test_translate.py`: `detect_lang` on Korean / English / mixed text; `translate`
  with an INJECTED fake translator (no real model load) for ko→en and en→ko
  direction selection; graceful `""` on failure and on empty input.
- `test_models.py`: `embed_text()` includes `description_translated` when set and
  omits it when empty.
- `test_sync.py`: with `translate` stubbed, only added/changed records are
  translated; unchanged records are not. With `SKILL_RAG_TRANSLATE=0`, no
  translation occurs.
- `uv run skill-rag eval`: add a few cross-lingual cases (Korean query → English
  fixture skill); recall@5 must not regress on existing English cases and should
  improve on the cross-lingual ones. Heavy MT model load is stubbed in unit
  tests; the eval may run the real model.

## Error handling

- Model load failure (offline, not cached) → log a warning, set
  `description_translated=""`, continue indexing. Because `LOCAL_FILES_ONLY=1`
  by default, the models must be fetched once during `make install`; document
  this so the skip path isn't hit silently in normal use.
- Empty/whitespace description → no translation.
- Mixed-language description → translate by dominant script (Hangul present →
  ko→en, else en→ko). Acceptable; not optimized further.

## Out of scope

- Author-provided bilingual frontmatter fields (future hybrid extension).
- Languages beyond Korean/English; general multilingual MT models.
- Translating the body or name.
- Query-side translation/expansion (this changes the document side only).
