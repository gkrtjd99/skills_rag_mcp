# Fast Multilingual Retrieval Plan

Status: Completed

- [x] Read the architecture, contracts, active plans, and quick references.
- [x] Measure baseline recall, no-match behavior, cold/warm latency, and token
  pressure points.
- [x] Add E5 query/passage prompts and automatic schema-profile migration.
- [x] Add Korean intent hints and stricter lexical rescue coverage.
- [x] Cache table metadata and BM25; use a bounded dense candidate shortlist.
- [x] Keep full bodies for BM25 but use compact description-only dense passages
  with a measured 64-token default cap.
- [x] Bound MCP hit descriptions and shorten tool descriptions.
- [x] Make local description translation explicit opt-in for the fast default.
- [x] Add focused unit tests and run fixture/performance verification.
- [x] Update current-state architecture, interface, product, README, and design
  decision documentation.
- [x] Make the public score follow hybrid RRF ordering without adding response
  fields.
- [x] Stress-test concurrent retrieval, malformed/long queries, random
  no-match inputs, unchanged sync, and BM25 scale; add a dense-only evidence
  gate for nonsense false positives.
