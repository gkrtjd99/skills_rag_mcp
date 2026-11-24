# Opt-in Rerank With Swappable Judges Plan

Status: Completed

- [x] Write 110 held-out queries for a 40-skill corpus before measuring.
- [x] Measure the shipped gate, the ungated shortlist, and a Jev fit judgment
      on the fixture and held-out corpora.
- [x] Split `retrieve.search` into ranking and gating; add `retrieve.shortlist`.
- [x] Add `rerank.py` (off by default, fail-open, cooldown) and route
      `search_skills` and `skill-rag query` through it.
- [x] Re-measure through the shipped code path at 16 candidates and set the
      default.
- [x] Extract the `Judge` protocol and registry (`skill_rag/judges/`); move Jev
      behind it; add the OpenAI Decisions judge and `module:factory` loading.
- [x] Cap descriptions of judged hits and report response size in the bench.
- [x] Extend the held-out set to the 45-skill corpus (133 queries) and measure
      gate, `jev`, and `openai` side by side.
- [x] Offline tests with every judge stubbed; the default suite needs no
      network, SDK, or key.
- [x] Update core beliefs, architecture, MCP contract, security notes, READMEs,
      and changelog.

Open follow-ups, not part of this change:

- Recalibrate or replace the local gate for users who keep rerank off.
- Opt-in lifecycle mode that moves skills out of harness directories so their
  descriptions stop loading natively (the largest remaining context cost).
- Improve first-stage recall for Korean queries (both remaining Jev misses).
- Make RRF tie-breaking deterministic.
- Measure on a corpus and query log that someone else wrote.
