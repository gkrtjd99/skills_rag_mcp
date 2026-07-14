# Reliability Hardening

Date: 2026-07-14
Status: In progress

## Problem

The offline test suite implicitly loaded the production `BAAI/bge-m3` model at
the time this spec was written (the production default is now
`intfloat/multilingual-e5-base`).
On a clean machine without that model cached, 54 of 212 tests fail before
exercising the behavior they claim to test. This prevents the suite from
providing portable evidence for the product's local-only guarantees.

The audit also found three correctness gaps:

- `open_table()` compares only Arrow field names, despite the derived-index
  contract requiring recreation on *any* schema drift. A changed vector
  dimension can therefore survive until a later opaque LanceDB failure.
- A malformed or non-UTF-8 `SKILL.md` can abort an entire corpus sync, although
  the parser contract says parse failures return `None`.
- The bootstrap exclusion is based only on its directory name, so an installed
  bootstrap whose frontmatter name is correct but directory is renamed can be
  returned by search.
- Lifecycle installation accepts an injected corpus path but previously indexed
  the configured global corpus instead, so collection and indexing could use
  different sources.
- The evaluator's percentile index reports a value below the actual p95 for
  small samples, weakening the stated latency success metric.
- MCP accepted invalid result counts, producing an `ok` response with no hits
  for `k=0` and Python negative-slice behavior for negative values. Its
  conversational guard also misclassified one-character non-ASCII topics.

## Decision

- Make unit and integration tests use a deterministic in-memory embedding
  model. Production continues to load only the configured local model; no
  cloud fallback is introduced.
- Compare the complete Arrow schema when opening an existing index table, so
  a vector type or dimension change recreates the disposable cache.
- Treat unreadable or invalid-UTF-8 skill files as invalid records and continue
  indexing the rest of the corpus.
- Exclude the bootstrap by both directory name and parsed frontmatter name.
- Pass the lifecycle corpus through to sync so its collection and indexing
  phases stay consistent; public runtime sync keeps its global default.
- Calculate p95 using the nearest-rank method (the smallest observation at or
  above the 95th percentile).
- Share a 1–50 result-count bound across retrieval, MCP, and CLI, and limit the
  single-letter conversational shortcut to ASCII answers.
- Record lifecycle-created corpus and harness links, and remove only entries
  whose current identity still matches that install record.
- Preserve conflicting MCP registrations rather than overwriting them; only
  lifecycle-created file registrations are eligible for lifecycle removal.

## Verification

- `uv run pytest -q` passes without a cached Hugging Face model.
- Focused tests cover same-name vector-dimension schema drift, malformed-file
  isolation, normalized fake embeddings, and two-sample p95 behavior.
- `uv run skill-rag eval --json` remains a production-model integration check;
  it may require the documented explicit model setup when the cache is empty.
