# Reliability Hardening Plan

Status: In progress

## Steps

- [x] Add a deterministic test-only embedding fixture that preserves vector
  shape and normalization without loading a Hugging Face model.
- [x] Detect full Arrow schema drift, including vector dimensions.
- [x] Skip unreadable and invalid-UTF-8 skill files during corpus scans.
- [x] Correct p95 percentile calculation and add a boundary test.
- [x] Keep injected lifecycle corpus paths consistent through the sync phase.
- [x] Validate result-count bounds consistently and avoid skipping single
  non-ASCII topics.
- [x] Preserve conflicting MCP registration entries and track file registrations
  created by lifecycle install.
- [ ] Run focused tests, the complete suite, and the fixture-evaluation path.
- [ ] Update the current-state design documentation and finalize this record.
