# Fast Multilingual Retrieval

Date: 2026-07-15
Status: Implemented and verified

## Problem

The MCP search path rebuilt BM25 and re-read the LanceDB metadata on every
query. The selected E5 model was also used without its required query/passage
prompts. A low dense threshold returned semantically adjacent skills for
unrelated requests, and long descriptions increased MCP context usage.

## Decision

- Encode E5 queries with `query:` and indexed skill text with `passage:`.
- Add a small local Korean intent vocabulary bridge for high-value terms such
  as regression, implementation, testing, and deployment. This is deterministic
  and local; it is not query-time network translation.
- Calibrate the default dense threshold to `0.78`, and require a lexical rescue
  to cover at least half of meaningful query terms after common function words
  are removed.
- Gate dense-only matches with at least one meaningful query-term match, a
  high-confidence cosine score of `0.86`, or a top-vs-runner-up cosine gap of
  `0.05`. The margin preserves strong matches in tiny corpora while arbitrary
  nonsense usually has a high but tightly clustered cosine baseline.
- Reuse the LanceDB table, indexed metadata, and BM25 object in the long-lived
  MCP process. Invalidate those caches on package-managed writes.
- Search only a bounded dense shortlist (`max(k*4, 20)` by default) while
  retaining full-corpus BM25 rescue.
- Cap returned hit descriptions at 280 characters by default. `get_skill`
  continues to return the complete source body.
- Report the query-relative normalized hybrid score in the existing `score`
  field. This keeps the public score aligned with RRF response ordering without
  adding another response field or increasing MCP result tokens.
- Disable local MarianMT description augmentation by default. Users can opt in
  with `SKILL_RAG_TRANSLATE=1` when the added index-time cost is worthwhile;
  native E5 remains the primary bilingual path.
- Mark the embedding profile in schema v11 so v6-v10 vectors are rebuilt instead
  of mixing old dense-text profiles with the new profile.
- Set the default dense input cap to 64 tokens and encode name/description by
  default. On the real 1,925-skill corpus,
  1,745 records hit the old 512-token cap; the shorter cap reduces the default
  attention sequence substantially while retaining the canonical trigger
  description. A
  corpus can opt into a short body prefix with `SKILL_RAG_DENSE_BODY_CHARS`.

## Verification

- `uv run pytest -q` passes with 257 tests.
- Public fixture: recall@5 = 1.0.
- Natural English/Korean fixture: recall@1 = 1.0 (30/30).
- Unrelated-query fixture: no-match accuracy = 1.0 (5/5).
- Synthetic 50-skill warm retrieval benchmark: p50 ≈ 10 ms, p95 ≈ 12 ms on
  the development machine; index construction is measured separately.
- Real 1,925-skill corpus: the first rebuild is measured separately from
  warm query latency; the dense encode payload is reduced to description-sized
  passages while BM25 retains full-body coverage.
- Real 1,925-skill corpus v11 migration search: 8.5 s on the development
  machine, followed by warm MCP queries in the tens of milliseconds.
- With the v11 index already present, a fresh MCP process measured 3.5 s for
  its first query and 16.6 ms p95 for subsequent queries. A 50-skill MCP
  benchmark measured 11.9 ms p95; hit descriptions stayed within the 280-char
  metadata cap.
- Actual 1,925-skill stress checks completed without errors: sequential warm
  p95 was 16.1 ms; 8 concurrent workers reached 119.6 ms p95; 16 workers
  reached 308.0 ms p95; and 32 workers reached 540.2 ms p95. Throughput stayed
  above 69 requests/second in these local runs.
- One hundred generated nonsense queries returned `no_match` after the
  dense-only evidence gate was added. Queries up to roughly 100,000 characters
  completed without exceptions; unchanged-corpus sync remained about 365 ms.
- BM25 synthetic scale checks up to 25,000 short documents completed in about
  100 ms to build and 13 ms per query; full-body memory growth remains a
  corpus-size consideration.
- No new dependency or cloud call was introduced.
