# Changelog

## [Unreleased]

## [0.4.0] - 2026-11-26

Search can now use a judge model, and with one it comes close to a harness
that loads every skill description while loading far fewer wrong skills. A
plain install has no judge and does not reach these numbers; `skill-rag
status` says so.

### Added

- Opt-in judge model, `SKILL_RAG_RERANK`. Off by default; any failure falls
  back to the local result.
  - `jev`: TypeSafe Jev (`rerank` extra, `TYPESAFE_API_KEY`).
  - `openai`: OpenAI Decisions API (`OPENAI_API_KEY`, no extra package).
  - `package.module:factory`: any model implementing `skill_rag.judges.Judge`.
- With a judge, the default style is `candidates`
  (`SKILL_RAG_RERANK_STYLE`): the judge scans every skill
  (`SKILL_RAG_RERANK_SCAN_MAX`, up to 500), the 16 it ranks highest are
  judged for fit, and those at or above 0.5 are returned best first, at most
  8, as `status: "candidates"` with descriptions capped at 120 characters.
  The calling agent chooses.
- `SKILL_RAG_RERANK_STYLE=single`: one skill at or above 0.9
  (`SKILL_RAG_RERANK_THRESHOLD`, `SKILL_RAG_RERANK_MAX_HITS`); otherwise the
  best one at or above `SKILL_RAG_RERANK_UNCERTAIN_FROM` (0.7) as
  `status: "uncertain"`, marked `"confidence": "low"`.
- A skill the request names outright (`/name`, `$name`, "the name skill",
  "name 스킬") is returned without a judgment, with or without a judge. A
  bare mention of a name does not count. `SKILL_RAG_EXPLICIT=0` turns it off.
- `skill-rag adopt [names] [--from DIR]` moves skills out of harness or
  project skill directories into `~/.skills/`, so the harness stops loading
  their descriptions into every session; `skill-rag restore` moves them back.
  `uninstall` restores adopted skills first and never deletes one it cannot
  restore, even with `--purge`.
- `skill-rag install --no-collect` sets up the bootstrap skill and MCP
  registration without linking harness and plugin skills into the store.
- Local usage log (`var/usage.jsonl`, `SKILL_RAG_USAGE_LOG=stats|full|off`) of
  what was suggested and what was then loaded, and `skill-rag usage` to
  summarize it per skill. No request text unless `full`.
- Skills already loaded in the current session are not suggested again
  (`SKILL_RAG_EXCLUDE_LOADED`).
- `get_skill` also returns `path`, the skill's directory, so bundled scripts
  and references resolve for skills no harness loads natively.
- `skill-rag status` reports the judge's readiness and where data would be
  sent. `status` and `install` print notes when the setup will not deliver
  the measured results: no active judge, fewer than 50 skills, a corpus above
  the scan limit, or an installed bootstrap skill older than this version.
- `SKILL_RAG_LOCAL_CANDIDATES` (off by default): without a judge, return the
  top N of the local ranking as uncertain candidates instead of the gate's
  hits. Fewer wrong loads, fewer useful ones.

### Changed

- Dense inputs default to 128 tokens with a 300-character body prefix (was 64
  and none); the index rebuilds itself on the next sync and indexing takes
  about twice as long. Fixture evaluations are unchanged at 1.000.
- `skill-rag query` follows the same search path as the MCP tool, including
  the judge when enabled.
- The bootstrap skill explains the `candidates` and `uncertain` statuses.
  An existing install keeps its old copy until `skill-rag install
  --refresh-bootstrap` is run.
- The READMEs open with purpose, when to use it, features, and measured
  effect.

### Removed

- The GitHub Actions workflow. `make check` runs the same steps locally
  (lockfile, tests, build, dry-run install).

### Privacy

- Without a judge nothing leaves the machine, as before.
- With a judge, every search sends the request text and the name and first
  120 characters of description of every skill (scan on, the default) or of
  the 16 shortlisted skills (scan off) to the chosen provider. Skill bodies
  and paths are never sent. See `SECURITY.md`.

### Upgrading from 0.3.0

- `git pull`, `make install`, then `uv sync --extra rerank` if you use `jev`
  (`make install` removes the extra).
- `uv run skill-rag install --refresh-bootstrap` to replace the installed
  bootstrap skill; back it up first if you edited it.
- `search_skills` can now answer `candidates` and `uncertain` in addition to
  `ok` and `no_match`, but only when a judge is configured.

### Measured

All with a model standing in for the calling agent (one call, empty context)
and requests written by another model; 350 skills; `jev`. Each protocol was
committed before its data existed. Rates are of what the agent loads.

| | Useful skill loaded | Wrong skill loaded when none matches |
|---|---|---|
| `candidates` style, first corpus / second corpus | 91.1% / 88.8% | 9.4% / 10.4% |
| `single` style | 74.9% / 71.4% | 0.0% / 4.2% |
| No search, every description in context | 94.8% / 93.9% | 54.2% / 43.8% |

- Without a judge, on another test set: 69.6% useful and 14.4% wrong loads,
  against 93.8% and 34.0% for every description in context.
- Cost with `jev` and the scan: about 18,000 to 21,000 input tokens and
  0.55 s per search. Standing context: about 160 tokens per search instead of
  about 34,000.
- The second corpus shares no repository with the first; no setting was
  changed for it (`docs/benchmarks/2026-11-25-second-corpus-results.md`).
- Not measured: real harness sessions, the `openai` judge in the
  `candidates` style, other corpus sizes.
- Earlier measurements of retrieval alone, the scale benchmark (50 to 350
  skills), and the negative results are in `docs/benchmarks/`.

## [0.3.0] - 2026-07-15

### Changed

- Use E5 `query:`/`passage:` prompts and schema v11 metadata so stale vector
  profiles rebuild automatically instead of being mixed with new queries.
- Limit dense passages to name and description by default, cap inputs at 64
  tokens, and retain the complete body for BM25 keyword rescue.
- Cache LanceDB metadata and BM25 structures between MCP calls and search a
  bounded dense shortlist while preserving full-corpus lexical rescue.
- Add deterministic Korean intent expansion and stricter meaningful-term
  coverage for multilingual matching and no-match decisions.
- Require lexical evidence or high dense confidence for dense-only matches,
  or a strong top-vs-runner-up margin in tiny corpora, preventing arbitrary
  nonsense queries from returning semantic false hits.
- Make local description translation opt-in with `SKILL_RAG_TRANSLATE=1`.
- Cap MCP hit descriptions at 280 characters and return a query-relative
  hybrid score aligned with the final RRF result order.

### Performance

- Reduce average dense indexing input from roughly 497 to 52 tokens on the
  1,925-skill corpus.
- Reduce the measured first search on a prepared real index from 51.2 seconds
  to 3.5 seconds, with subsequent searches at roughly 16.6 ms p95.
- On the actual 1,925-skill corpus, warm sequential p95 was 16.1 ms; 8, 16,
  and 32 concurrent workers measured 119.6 ms, 308.0 ms, and 540.2 ms p95
  respectively, without request errors.
- One hundred generated nonsense queries returned `no_match`; long-query and
  unchanged-sync checks completed without exceptions.
- Preserve recall@5 = 1.000, natural-language recall@1 = 1.000, and no-match
  accuracy = 1.000 on the repository evaluation fixtures.

### Fixed

- Prevent evaluator/sync clock tests from monkeypatching the process-wide
  `time.monotonic`, which could break LanceDB's background event loop.
- Keep generated indexes, benchmark output, and local model caches out of Git.

## [0.2.0] - 2026-07-14

### Changed

- Use `intfloat/multilingual-e5-base` as the default local embedding model.
- Keep `SKILL_RAG_MODEL` as an override for BGE-M3 or another compatible model.
- Rebuild a stale LanceDB cache automatically when the embedding dimension
  changes.
- Add disposable Docker model benchmarks and a bilingual natural-language
  evaluation fixture.
- Keep native Claude/Codex skill loading as a fallback; skill-rag remains a
  lazy MCP retrieval path rather than a native-loader replacement.

## [0.1.0] - Previous development baseline

- Initial local MCP RAG lifecycle, corpus collection, hybrid retrieval, and
  Claude/Codex bootstrap integration.
